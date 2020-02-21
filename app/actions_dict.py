from typing import List
from dataclasses import dataclass, field


@dataclass
class Action:
    name: str
    title: str
    message: str


@dataclass
class Actions:
    action_map: field(default_factory=dict)


action_list: List[Action] = [
    Action(
        'crop',
        '✂ Cut audio by time',
        'Pass start and end seconds as one message like: `15-120`',
    ),
    Action(
        'makevoice',
        '🎙 Cut audio and return fragment as voice message',
        'Pass start and end seconds please as one message like that: `15-120`.\n'
        '`0` means - convert entire file to a voice message.',
    ),
    Action(
        'thumbnail',
        '🏞 📎 Set thumbnail for audio file via Telegram API',
        'Send one photo',
    ),
    Action(
        'setcover',
        '🏞 🔨 Embed image into file as a front cover',
        'Send one photo',
    ),
    Action(
        'makeopus',
        '📣 Convert audio to Opus OGG format',
        'Send audio file',
    ),
    Action(
        'makerounded',
        '📺 Make "roundy" video note from a video',
        'Pass start and end seconds in one minute range like: `70-110`.\n'
        '`0` means one minute default.'
    ),
]

actions: Actions = Actions({x.name: x for x in action_list})
