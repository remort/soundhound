import os
from typing import Tuple

from app.exceptions.base import ConfigurationError

DEBUGLEVELS: Tuple[str] = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
DEBUGLEVEL: str = os.getenv('DEBUGLEVEL', 'DEBUG')
if DEBUGLEVEL and DEBUGLEVEL not in DEBUGLEVELS:
    raise ConfigurationError('invalid_debuglevel', {'LEVELS': DEBUGLEVELS})

TOKEN: str = os.getenv('TOKEN', None)
if not TOKEN:
    raise ConfigurationError('no_token', {'token': TOKEN})

SERVER_NAME: str = os.getenv('SERVER_NAME')
PUBLIC_PORT: int = int(os.getenv('PUBLIC_PORT'))

OPERATION_LOCK_TIMEOUT: int = 600

SIZE_1MB: int = 1048576
SIZE_20MB: int = 20971520
SIZE_50MB: int = 52428800

USAGE_INFO: str = """
SoundHound bot.

This bot helps you to perform some small actions with your audio files in Telegram.

Type something to call a dog (doc) or use a /start command and you'll get Action keyboard, which allows you:

- *Cut audio files* by specified period of time in seconds, returning a fragment of the same format.
- Same, returning Telegram *Voice message*.
- *Set thumbnail* for an audio file. Thumbnail shows in Telegram only and not being placed into your file.
- *Set cover*. Same as above with also including a picture inside audio file as front cover.
- Convert audio file to *Opus OGG* format as, by far, most advanced audio format. 

Audio file can be either of `MP3`, `FLAC`, `OGG`, `WAV` or `M4A` format and get received by Sound Hound one by one.

Thumbnail picture can be any photo acceptable by Telegram in any reasonable dimensions.
It'll be converted to 1:1 320x320 JPEG if needed.

/info shows this message.

Feedback: @redahead.
"""
