import asyncio
from asyncio.subprocess import Process
import logging
import shutil
from typing import Tuple, Any

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
    async def __run_ffmpeg(*params: str, file_content) -> bytes:
        """
        Приватный метод запуска ffmpeg с переданными ему параметрами
        Вызывается из приватных методов конкретных action'ов этого класса.
        Работает через pipe принимает байты и возвращает байты обработанного содержимого.
        """
        log.debug(f'Run ffmpeg with args: {params}')
        try:
            process: Process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-hide_banner', '-y', '-i', 'pipe:0', *params, 'pipe:1',
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await process.communicate(input=file_content)

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
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-acodec', 'copy', '-f', suffix,
            file_content=audio_filename,
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
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-map', 'a', '-c:a', 'libopus',
            '-b:a', str(bitrate), '-vbr', 'off', '-f', 'oga',
            file_content=audio_filename,
        )

    async def handle_file(self, file: bytes, file_meta: dict, action: str, parameters: Any) -> bytes:
        """
        Публичный метод, принимающий action и соотв. ему paramaters из внешнего кода.
        Роутит по приватным методам класса, получает от них обработанные байты, и возвращает их обратно в внешний код.
        """
        # TODO: type hinting for `parameters`. Many actions possible.
        audio: bytes = b''
        suffix: str = file_meta['suffix'].replace('.', '')

        # # m4a (aac) это adts у ffmpeg
        if suffix == 'm4a':
            suffix = 'adts'

        if action == 'crop':
            audio = await self._crop_file(file, suffix, parameters)

        elif action == 'makevoice':
            audio = await self._make_voice(file, parameters)

        else:
            log.error(f'Task handler for action: {action} is not implemented')

        return audio
