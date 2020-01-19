import asyncio
from asyncio.subprocess import Process
import logging
import shutil
from tempfile import NamedTemporaryFile
from typing import Any, Optional, Tuple

from app.config import DEBUGLEVEL
from app.exceptions.audio import FfmpegError, FfmpegExecutableNotFoundError

log = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class AudioHandler:
    def __init__(self):
        if not shutil.which('ffmpeg'):
            raise FfmpegExecutableNotFoundError('FFMPEG executable not found in the system.')
        log.info('FFMPEG found.')
        self.suffix_to_format: dict = {'.m4a': 'adts'}

    @staticmethod
    async def __run_ffmpeg(*params: str, file_content: bytes, suffix: str) -> bytes:
        """
        Приватный метод запуска ffmpeg с переданными ему параметрами
        Вызывается из приватных методов конкретных action'ов этого класса.
        Работает через pipe. Принимает байты и возвращает байты обработанного содержимого.
        В случае некоторых форматов данных, например m4a(adts), может принимать данные только через файл.
        file_content - байты аудиофайла подаваемые ffmpeg на stdin.
        """
        file_input_suffixes = ('.m4a',)
        temp_file: Optional[object] = None
        input_source: str = 'pipe:0'
        stdin: Optional[str] = asyncio.subprocess.PIPE
        input: Optional[bytes] = file_content

        if suffix in file_input_suffixes:
            temp_file: object = NamedTemporaryFile(suffix=suffix)
            temp_file.write(file_content)
            input_source = temp_file.name
            stdin = None
            input = None

        try:
            args = ('ffmpeg', '-hide_banner', '-y', '-i', input_source, *params, 'pipe:1')
            log.debug(f'Run ffmpeg subprocess with args: {args}')

            process: Process = await asyncio.create_subprocess_exec(
                *args,
                stdin=stdin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await process.communicate(input=input)

        except Exception as error:
            log.error(f'Ffmpeg failed, err: {error}, params: {params}')
            raise FfmpegError(
                'Ffmpeg call failed.',
                {
                    'ffmpeg_error': error,
                    'parameters': params,
                }
            )
        finally:
            if temp_file:
                temp_file.close()
            if process.returncode is None:
                await process.terminate()

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

    async def _crop_file(self, audio_filename: str, suffix: str, _format: str, time_range: Tuple[int]) -> bytes:
        """
        Запускает подпроцесс ffmpeg для обрезания аудио файла в заданном диапазоне.
        Возвращает байты обрезанного файла.
        """
        return await self.__run_ffmpeg(
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-acodec', 'copy', '-f', _format,
            file_content=audio_filename,
            suffix=suffix,
        )

    async def _make_voice(self, audio_filename: str, suffix: str, time_range: Tuple[int]) -> bytes:
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
            suffix=suffix,
        )

    async def handle_file(self, file: bytes, file_meta: dict, action: str, parameters: Any) -> bytes:
        """
        Публичный метод, принимающий action и соотв. ему paramaters из внешнего кода.
        Роутит по приватным методам класса, получает от них обработанные байты, и возвращает их обратно в внешний код.
        """
        # TODO: type hinting for `parameters`. Many actions possible.
        audio: bytes = b''
        suffix: str = file_meta['suffix']

        _format: str = file_meta['suffix'].replace('.', '')
        if suffix in self.suffix_to_format:
            _format = self.suffix_to_format[suffix]

        if action == 'crop':
            audio = await self._crop_file(file, suffix, _format, parameters)

        elif action == 'makevoice':
            audio = await self._make_voice(file, suffix, parameters)

        else:
            log.error(f'Task handler for action: {action} is not implemented')

        return audio
