from typing import Optional

from app.exceptions.base import SoundHoundError


class FfmpegError(SoundHoundError):
    """Выбрасывается при общем сбое запуска ffmpeg."""
    def __init__(self, err_msg: str, extra: dict):
        super(FfmpegError, self).__init__(self, err_msg, extra)


class FfmpegExecutableNotFoundError(SoundHoundError):
    """Выбрасывается если при инициализации класса Audion в системе не был найден ffmpeg."""
    def __init__(self, err_msg: str):
        super(FfmpegExecutableNotFoundError, self).__init__(self, err_msg)
