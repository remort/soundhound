from dataclasses import dataclass, field
from typing import Any, Dict
from typing import Tuple as Tuple

from marshmallow import Schema
from marshmallow.fields import Boolean
from marshmallow.fields import Dict as DictField
from marshmallow.fields import Integer, String
from marshmallow.fields import Tuple as TupleField

from app.serializers.utils import BytesField


@dataclass
class UserStateModel:
    id: int
    action: str = None
    actions_sent: bool = False
    time_range: Tuple[int] = field(default=None)
    audio_metadata: Dict[str, Any] = field(default_factory=dict)
    audio_file: bytes = None
    thumbnail_file: bytes = None
    tg_thumbnail_file: bytes = None


class UserStateSchema(Schema):
    id = Integer()
    action = String(required=False, allow_none=True)
    actions_sent = Boolean(required=False)
    time_range = TupleField((Integer(), Integer()), required=False, allow_none=True)
    audio_metadata = DictField(keys=String(), values=String(), required=False, allow_none=True)
    audio_file = BytesField(required=False, allow_none=True)
    thumbnail_file = BytesField(required=False, allow_none=True)
    tg_thumbnail_file = BytesField(required=False, allow_none=True)
