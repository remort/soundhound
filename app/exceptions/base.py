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
