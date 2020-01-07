from typing import Optional

from app.exceptions.base import SoundHoundError


class ConfigurationError(SoundHoundError):
    """Выбрасывается в config.py если обнаружена ошибка конфигурации."""
    def __init__(self, err_msg: str, extra: dict):
        super(ConfigurationError, self).__init__(self, err_msg, extra)


class TGNetworkError(SoundHoundError):
    """Ошибка связанная с сетевым взаимодействием с Telegram API."""
    def __init__(self, err_msg: str, response: dict, orig_exc: Exception):
        super(TGNetworkError, self).__init__(self, err_msg, response, orig_exc)


class TGApiError(SoundHoundError):
    """Telegram API вернул тело ответа без 'ok' в теле."""
    def __init__(self, err_msg: str, response: dict):
        super(TGApiError, self).__init__(self, err_msg, response)


class UpdateValidationError(SoundHoundError):
    """Тело Update пришедшее в webhook от Telegram не прошло проверку на валидность/не смогло быть распарсено."""
    def __init__(self, err_msg: str, update: dict):
        super(UpdateValidationError, self).__init__(self, err_msg, update)


class RoutingError(SoundHoundError):
    """Ошибка роутинга в бизнес-логике телеграм-бота"""
    def __init__(self, err_msg: str, update: dict):
        super(RoutingError, self).__init__(self, err_msg, update)


class ParametersValidationError(SoundHoundError):
    """Выбрасывается при невозможности распарсить параметры к выбранному действию."""

    def __init__(self, err_msg: str, extra: dict, orig_exc: Optional[Exception] = None):
        super(ParametersValidationError, self).__init__(self, err_msg, extra, orig_exc)


class WrongFileError(SoundHoundError):
    """Если скачиваемый файл не поддерживается."""
    def __init__(self, err_msg: str, extra: dict):
        super(WrongFileError, self).__init__(self, err_msg, extra)


class FileSizeError(SoundHoundError):
    """Если отправляемый файл превысил размер."""
    def __init__(self, err_msg: str, extra: dict):
        super(FileSizeError, self).__init__(self, err_msg, extra)


class NotImplementedYetError(SoundHoundError):
    """Когда запрошенный код еще не написан."""
    def __init__(self, err_msg: Optional[str] = 'This is not implemented yet.'):
        super(NotImplementedYetError, self).__init__(self, err_msg)
