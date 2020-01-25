import asyncio
from asyncio.subprocess import Process
import logging
import shutil
from tempfile import NamedTemporaryFile
from typing import Any, Optional, Tuple, Union

from app.config import DEBUGLEVEL
from app.exceptions.audio import (
    AudioHandlerError,
    ExecutableNotFoundError,
    SubprocessError,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class AudioHandler:
    def __init__(self):
        if not shutil.which('ffmpeg'):
            raise ExecutableNotFoundError('"ffmpeg" executable not found in the system.')
        if not shutil.which('ffprobe'):
            raise ExecutableNotFoundError('"ffprobe" executable not found in the system.')
        log.info('"ffmpeg" and "ffprobe" found.')
        self.suffix_to_format: dict = {'.m4a': 'adts'}

    @staticmethod
    async def __run_command(command: str, file_content: bytes, suffix: str, *params: Tuple[str]) -> bytes:
        """
        Вызывает ffmpeg/ffprobe с переданными параметрами и возвращает результат или бросает эксепшн.
        По suffix определяем форматы, которые должны быть переданы ff,peg в качестве файла на ФС.

        Команды работают через pipe кроме некоторых форматов аудио для ffmpeg.
        ffprobe возвращает битрейт аудио потока в bit/s

        :param command: 'ffmpeg' или 'ffprobe'.
        :param params: Параметры запуска, разбитые в формате subprocess.
        :param file_content: байты аудиоконтента.
        :param suffix: расширение файла.
        :return: bytes stdout команды.
        """
        stdin: Optional[str] = asyncio.subprocess.PIPE
        pipe_input: Optional[bytes] = file_content
        temp_file: object = None
        process: Process = None

        if command == 'ffmpeg':
            ffmpeg_input_source: str = 'pipe:0'

            if suffix in ('.m4a',):
                temp_file: object = NamedTemporaryFile(suffix=suffix)
                temp_file.write(file_content)
                ffmpeg_input_source = temp_file.name
                stdin = None
                pipe_input = None
            args = ('-hide_banner', '-y', '-i', ffmpeg_input_source, *params, 'pipe:1')

        elif command == 'ffprobe':
            args = ('-v', 'error', *params, '-')
        else:
            raise AudioHandlerError('Unknown command.', {'command': command})

        try:
            args = (command, *args)
            log.debug(f'Run {command} subprocess with args: {args}')

            process: Process = await asyncio.create_subprocess_exec(
                *args,
                stdin=stdin,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await process.communicate(input=pipe_input)

        except Exception as error:
            raise SubprocessError(
                f'{command} call failed.',
                {
                    'error': error,
                    'suffix': suffix,
                }
            )

        finally:
            if process:
                if process.returncode is None:
                    await process.terminate()
            if temp_file:
                temp_file.close()

        exc_extra: dict = {
            'stdout': out,
            'stderr': err,
            'suffix': suffix,
        }

        if process.returncode != 0:
            log.error(f'{command} return code is not 0. Debug: {exc_extra}')
            if not all((len(out) > 0, isinstance(out, bytes))):
                raise SubprocessError(f'{command} return code is not 0.', exc_extra)

        if not out:
            raise SubprocessError(f'{command} returned zero output.', exc_extra)

        return out

    async def _crop_file(self, audio: bytes, suffix: str, _format: str, time_range: Tuple[int]) -> bytes:
        """
        Запускает подпроцесс ffmpeg для обрезания аудио файла в заданном диапазоне.
        Возвращает байты обрезанного файла.
        """
        return await self.__run_command(
            'ffmpeg',
            audio,
            suffix,
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-acodec', 'copy', '-f', _format,
        )

    async def _make_voice(self, audio: bytes, suffix: str, time_range: Tuple[int]) -> bytes:
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

        return await self.__run_command(
            'ffmpeg',
            audio,
            suffix,
            '-ss', str(time_range[0]), '-to', str(time_range[1]), '-map', 'a', '-c:a', 'libopus',
            '-b:a', str(bitrate), '-vbr', 'off', '-f', 'oga',
        )

    async def _get_bitrate(self, audio: bytes, suffix: str) -> Optional[int]:
        """У flac почему то не определяет bitrate но это и не нужно, т.к. все равно lossless."""
        if suffix == '.flac':
            return None

        output: bytes = await self.__run_command(
            'ffprobe',
            audio,
            suffix,
            '-show_entries', 'stream=bit_rate', '-select_streams', 'a', '-of', 'csv',
        )

        field_name: str
        bitrate: Union[str, int]
        try:
            field_name, bitrate = output.decode().strip().split(',')
            bitrate = int(bitrate)
        except ValueError:
            raise AudioHandlerError('Unable to parse ffprobe output.', output)

        return bitrate

    async def _make_opus(self, audio: bytes, file_meta: dict, suffix: str) -> bytes:
        """Если у нас невысокий битрейт (ниже 192 Кбит), кодируем в 96К Opus. Иначе в 128K Opus."""

        output_bitrate: str = '128K'
        input_bitrate: int = await self._get_bitrate(audio, suffix)

        if input_bitrate and input_bitrate < 192000:
            output_bitrate: str = '96K'

        return await self.__run_command(
            'ffmpeg',
            audio,
            suffix,
            '-c:a', 'libopus', '-b:a', output_bitrate, '-vbr', 'off', '-f', 'oga',
        )

    async def handle_file(self, file: bytes, file_meta: dict, action: str, parameters: Any) -> bytes:
        """
        Публичный метод, принимающий action и соотв. ему paramaters из внешнего кода.
        Роутит по приватным методам класса, получает от них обработанные байты, и возвращает их обратно в внешний код.
        """
        audio: bytes = b''
        suffix: str = file_meta['suffix']

        _format: str = file_meta['suffix'].replace('.', '')
        if suffix in self.suffix_to_format:
            _format = self.suffix_to_format[suffix]

        if action == 'crop':
            audio = await self._crop_file(file, suffix, _format, parameters)

        elif action == 'makevoice':
            audio = await self._make_voice(file, suffix, parameters)

        elif action == 'makeopus':
            audio = await self._make_opus(file, file_meta, suffix)

        else:
            log.error(f'Task handler for action: {action} is not implemented')

        return audio
