from typing import Optional


class SoundHoundError(Exception):
    """Базовый класс для всех исключений этого приложения."""
    def __init__(
            self,
            exc: Exception,
            err_msg: str,
            extra: Optional[dict] = None,
            orig_exc: Optional[Exception] = None,
    ):
        self.exc = exc
        self.err_msg = err_msg
        self.extra = extra
        self.orig_exc = orig_exc

    def __str__(self) -> str:
        return str(self.exc.__class__)


class RoutingError(SoundHoundError):
    """Ошибка роутинга в бизнес-логике телеграм-бота"""
    def __init__(self, err_msg: str, update: dict):
        super(RoutingError, self).__init__(self, err_msg, update)


class ParametersValidationError(SoundHoundError):
    """Выбрасывается при невозможности распарсить параметры к выбранному действию."""

    def __init__(self, err_msg: str, extra: dict, orig_exc: Optional[Exception] = None):
        super(ParametersValidationError, self).__init__(self, err_msg, extra, orig_exc)


class ConfigurationError(SoundHoundError):
    """Выбрасывается в config.py если обнаружена ошибка конфигурации."""
    def __init__(self, err_msg: str, extra: dict):
        super(ConfigurationError, self).__init__(self, err_msg, extra)


class NotImplementedYetError(SoundHoundError):
    """Когда запрошенный код еще не написан."""
    def __init__(self, err_msg: Optional[str] = 'This is not implemented yet.'):
        super(NotImplementedYetError, self).__init__(self, err_msg)

