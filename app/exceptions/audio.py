from app.exceptions.base import SoundHoundError


class AudioHandlerError(SoundHoundError):
    """Выбрасывается при общих ошибках в коде mediahandler.py."""
    def __init__(self, err_msg: str, extra: dict):
        super(AudioHandlerError, self).__init__(self, err_msg, extra)


class SubprocessError(SoundHoundError):
    """Выбрасывается при ошибках связанных с запуском/выполнением и получением ответа от ffmpeg/ffprobe."""
    def __init__(self, err_msg: str, extra: dict):
        super(SubprocessError, self).__init__(self, err_msg, extra)


class ExecutableNotFoundError(SoundHoundError):
    """Выбрасывается если при инициализации класса Audion в системе не был найден ffmpeg."""
    def __init__(self, err_msg: str):
        super(ExecutableNotFoundError, self).__init__(self, err_msg)
