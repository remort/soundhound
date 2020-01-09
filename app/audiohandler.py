import asyncio
from asyncio.subprocess import Process
import logging
from pathlib import Path
import shutil
from typing import Dict, Optional, Tuple

from app.config import DEBUGLEVEL
from app.exceptions.audio import FfmpegError, FfmpegExecutableNotFoundError

log = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class AudioHandler:
    def __init__(self):
        if not shutil.which('ffmpeg'):
            raise FfmpegExecutableNotFoundError('FFMPEG executable not found in the system.')
        log.info('FFMPEG found.')

    @staticmethod
    async def __run_ffmpeg(self, *params: str) -> bytes:
        """
        Приватный метод запуска ffmpeg с переданными ему параметрами
        Вызывается из приватных методов конкретных action'ов этого класса.
        Работает через pipe и возвращает сами байты обработанного содержимого.
        """
        log.debug(f'Run ffmpeg with args: {params}')
        try:
            process: Process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-hide_banner', '-y', *params, 'pipe:1',
                stdin=None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await process.communicate()

        except Exception as error:
            log.error(f'Ffmpeg failed, err: {error}, params: {params}')
            raise FfmpegError(
                'Ffmpeg call failed.',
                {
                    'ffmpeg_error': error,
                    'parameters': params,
                }
            )

        log.debug(f'File processed with return code {process.returncode}')

        exc_extra: dict = {
            'ffmpeg_stdout': out,
            'ffmpeg_stderr': err,
            'parameters': params,
        }

        if process.returncode != 0:
            log.error(f'Ffmpeg return code is not 0, stderr: {err}, params: {params}, lenout: {len(out)}')
            if not all((len(out) > 0, isinstance(out, bytes))):
                raise FfmpegError('Ffmpeg return code is not 0.', exc_extra)

        if not out:
            raise FfmpegError('Ffmpeg returned zero output.', exc_extra)

        return out

    async def _crop_file(self, audio_filename: str, suffix: str, time_range: Tuple[int]) -> bytes:
        """
        Запускает подпроцесс ffmpeg для обрезания аудио файла в заданном диапазоне.
        Возвращает байты обрезанного файла.
        """
        return await self.__run_ffmpeg(
            '-i', audio_filename,
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-acodec', 'copy', '-f', suffix
        )

    async def _make_voice(self, audio_filename: str, time_range: Tuple[int]) -> bytes:
        """
        Обрезает файл по времени, а так же конвертирует в opus ogg, вычисляя оптимальный битрейт по времени
        результирующего фрагмента.

        Телеграм имеет ограничение на размер 1 Мб макс. для голосовых сообщений и формат - ogg audio.
        Кодировать необходимо кодеком opus, иначе не видна спектрограмма сообщения в телеграме.
        Возможные битрейты: 500 - 512000. Я выбрал мин. ограничение в 8000 бит.сек.
        8000000(бит в 1 Мб) / 8000(бит/с) = 1000(сек):
            Максимально допустимая длина фрагмента ogg для создания voice файла.
        """
        MAX_BITRATE: int = 512000
        bitrate: int = 8000000 // (int(time_range[1]) - int(time_range[0]))

        if bitrate >= MAX_BITRATE:
            bitrate = MAX_BITRATE

        return await self.__run_ffmpeg(
            '-i', audio_filename,
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-map', 'a', '-c:a', 'libopus',
            '-b:a', str(bitrate), '-vbr', 'off', '-f', 'oga'
        )

    async def _set_cover(self, audio_filename: str, suffix: str, params: Dict[str, str]) -> Optional[bytes]:
        """
        ffmpeg -i XXX.mp3 -i YYY.png -acodec copy -map 0 -map 1 -disposition:v:1 attached_pic XXX.mp3

        Не работает через pipe. Файл с картинкой получается битый, не проигрывается. Вероятно надо юзать thumb телеграма.
        https://stackoverflow.com/questions/55973987/unable-to-set-thumbnail-image-to-mp3-file-using-ffmpeg-sending-its-output-to-co
        """
        log.warning(f"At set cover: suffix: {suffix}, pic file: {params['file_name']}, aufname: {audio_filename}")

        try:
            process: Process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-hide_banner', '-y',
                '-i', audio_filename, '-i', params['file_name'],
                '-codec', 'copy', '-map', '0', '-map', '1',
                '-disposition:v:1', 'attached_pic',
                f'/tmp/file.{suffix}',
            )
            out, err = await process.communicate()

        except Exception as error:
            log.error(f'Ffmpeg failed, err: {error}')
            return None

        log.debug(f'File processed with return code {process.returncode}')

        if process.returncode != 0:
            log.error(f'Ffmpeg return code is not 0, stderr: {err}')
            return None

        with open(f'/tmp/file.{suffix}', 'rb') as file_with_thumbnail:
            return file_with_thumbnail.read()

        # TODO: переделать на такой вариант, разобравшись почему файлы полученные через pipe не играются в телеграмме
        # return await run_ffmpeg(
        #     '-i', audio_filename, '-i', params['file_name'],
        #     '-codec', 'copy', '-map', '0', '-map', '1',
        #     '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"',
        #     '-disposition:v:1', 'attached_pic', '-f', suffix
        # )

    async def handle_file(self, file: object, action: str, parameters) -> bytes:
        """
        Публичный метод, принимающий action и соотв. ему paramaters из внешнего кода.
        Роутит по приватным методам класса, получает от них обработанные байты, и возвращает их обратно в внешний код.
        """
        # TODO: type hinting for `parameters`. Many actions possible.
        audio: bytes = b''
        audio_filename: str = file.name
        suffix: str = Path(file.name).suffix.lower().replace('.', '')
        # m4a (aac) это adts у ffmpeg
        if suffix == 'm4a':
            suffix = 'adts'

        if action == 'crop':
            audio = await self._crop_file(audio_filename, suffix, parameters)

        elif action == 'makevoice':
            audio = await self._make_voice(audio_filename, parameters)

        elif action == 'set_cover':
            audio = await self._set_cover(audio_filename, suffix, parameters)

        else:
            log.error(f'Task handler for action: {action} is not implemented')

        return audio
