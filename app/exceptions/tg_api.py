from typing import Optional

from app.exceptions.base import SoundHoundError


class TGNetworkError(SoundHoundError):
    """Ошибка связанная с сетевым взаимодействием с Telegram API."""
    def __init__(self, err_msg: str, extra: dict, orig_exc: Exception):
        super(TGNetworkError, self).__init__(self, err_msg, extra, orig_exc)


class TGApiError(SoundHoundError):
    """Telegram API вернул тело ответа без 'ok' в теле."""
    def __init__(self, err_msg: str, response: dict):
        super(TGApiError, self).__init__(self, err_msg, response)


class UpdateValidationError(SoundHoundError):
    """Тело Update пришедшее в webhook от Telegram не прошло проверку на валидность/не смогло быть распарсено."""
    def __init__(self, err_msg: str, update: dict):
        super(UpdateValidationError, self).__init__(self, err_msg, update)


class FileError(SoundHoundError):
    """Если скачиваемый/загружаемый файл не поддерживается/превышает размер и т.д."""
    def __init__(self, err_msg: str, extra: dict):
        super(FileError, self).__init__(self, err_msg, extra)
