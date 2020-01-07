from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

from marshmallow import Schema, post_load
from marshmallow.fields import Boolean, Integer
from marshmallow.fields import List as ListField, Tuple as TupleField
from marshmallow.fields import String

from app.serializers.utils import BytesField


@dataclass
class UserStateModel:
    id: int
    action: str = None
    actions_sent: bool = False
    time_range: List[int] = field(default_factory=tuple)
    audio_metadata: Dict[str, Any] = field(default_factory=dict)
    audio_file_sent: bool = False
    audio_file: bytes = None


class UserStateSchema(Schema):
    id = Integer()
    action = String(required=False, allow_none=True)
    actions_sent = Boolean(required=False)
    time_range = ListField(Integer(), required=False, allow_none=True)
    file_sent = Boolean(required=False)
    file = BytesField(required=False, allow_none=True)

    @post_load
    def make_user_state(self, data, **kwargs):
        return UserStateModel(**data)
