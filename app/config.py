import os
from typing import Tuple

from app.exceptions.api import ConfigurationError

DEBUGLEVELS: Tuple[str] = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
DEBUGLEVEL: str = os.getenv('DEBUGLEVEL', 'DEBUG')
if DEBUGLEVEL and DEBUGLEVEL not in DEBUGLEVELS:
    raise ConfigurationError('invalid_debuglevel', {'LEVELS': DEBUGLEVELS})

TOKEN: str = os.getenv('TOKEN', None)
if not TOKEN:
    raise ConfigurationError('no_token', {'token': TOKEN})

SERVER_NAME: str = os.getenv('SERVER_NAME')

OPERATION_LOCK_TIMEOUT: int = 600

USAGE_INFO: str = """
This bloat helps you to perform some small actions with your audio files in Telegram.

For now it can:
1. Receive single .mp3, .flac, .ogg (possibly opus encoded only?) and .m4a file.
2. Cut it by specified period of time in seconds, returning a fragment of the same format.
3. Returning fragment can be a Telegram voice audio (opus ogg).

Type something to call a dog (doc) or use a /start command.

Feedback: @redahead
"""
