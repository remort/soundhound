import asyncio
import logging
from typing import Dict, Optional, Any, Union

log = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')

MAX_DURATION = 1000


async def run_ffmpeg(*params: str) -> Optional[bytes]:
    log.info(f'Run ffmpeg with args: {params}')
    try:
        process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-hide_banner', '-y', *params, 'pipe:1',
            stdin=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await process.communicate()

    except Exception as error:
        log.error(f'Ffmpeg failed, err: {error}')
        return None

    log.debug(f'File processed with return code {process.returncode}')

    if process.returncode != 0:
        log.error(f'Ffmpeg return code is not 0, stderr: {err}')
        return None

    return out


async def crop_file(audio_filename: str, suffix: str, params: Dict[str, str]) -> bytes:
    # TODO: параметры в дикте хранить строкой чтобы обращаться по ключам а не по индексам
    # TODO: определять формат для -f как то. из расширения или майма
    log.debug(f"in cropper: {audio_filename}, params {params['start_time']}, {params['end_time']}")
    return await run_ffmpeg(
        '-i', audio_filename,
        '-ss', str(params['start_time']), '-to', str(params['end_time']), '-acodec', 'copy', '-f', suffix
    )


async def make_voice(audio_filename: str, params: Dict[str, str]) -> bytes:
    """
    Телеграм имеет ограничение на размер 1 Мб макс. для голосовых сообщений и формат - ogg audio.
    Кодировать необходимо кодеком opus, иначе не видна спектрограмма сообщения в телеграме.
    Возможные битрейты: 500 and 512000. Я выбрал мин. ограничение в 8000 бит.сек.
    8000000(бит в 1 Мб) / 8000(бит/с) = 1000(сек): Максимально допустимая длина фрагмента ogg для создания voice файла.

    """
    MAX_BITRATE = 512000

    log.debug(f"in voice maker: {audio_filename}, params {params['start_time']}, {params['end_time']}")
    bitrate = 8000000 // params['end_time'] - params['start_time']

    if bitrate >= MAX_BITRATE:
        bitrate = MAX_BITRATE

    return await run_ffmpeg(
        '-i', audio_filename,
        '-ss', str(params['start_time']), '-to', str(params['end_time']), '-map', 'a', '-c:a', 'libopus',
        '-b:a', str(bitrate), '-vbr', 'off', '-f', 'oga'
    )


async def set_cover(audio_filename: str, suffix: str, params: Dict[str, str]) -> Optional[bytes]:
    """
    ffmpeg -i XXX.mp3 -i YYY.png -acodec copy -map 0 -map 1 -disposition:v:1 attached_pic XXX.mp3

    Не работает через pipe. Файл с картинкой получается битый, не проигрывается. Вероятно надо юзать thumb телеграма.
    https://stackoverflow.com/questions/55973987/unable-to-set-thumbnail-image-to-mp3-file-using-ffmpeg-sending-its-output-to-co
    """
    log.warning(f"At set cover: suffix: {suffix}, pic file: {params['file_name']}, aufname: {audio_filename}")

    try:
        process = await asyncio.create_subprocess_exec(
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

    # TODO: переделать на такой вариант, разобравшись почему файлы полученные через pipe не играются в телеграме
    # return await run_ffmpeg(
    #     '-i', audio_filename, '-i', params['file_name'],
    #     '-codec', 'copy', '-map', '0', '-map', '1',
    #     '-id3v2_version', '3', '-metadata:s:v', 'title="Album cover"', '-metadata:s:v', 'comment="Cover (front)"',
    #     '-disposition:v:1', 'attached_pic', '-f', suffix
    # )


async def handle_file(audio_meta: Dict[str, Any], action: str, parameters) -> Union[bool, bytes]:
    audio = False
    audio_filename = audio_meta['file_name']
    suffix = audio_meta['file_suffix']

    if action == 'crop':
        audio = await crop_file(audio_filename, suffix, parameters)

    elif action == 'makevoice':
        audio = await make_voice(audio_filename, parameters)

    elif action == 'set_cover':
        audio = await set_cover(audio_filename, suffix, parameters)

    else:
        log.error(f'Task handler for action: {action} is not implemented')

    return audio
