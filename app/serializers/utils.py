from datetime import datetime

from marshmallow.fields import DateTime, Field, ValidationError


class Timestamp(DateTime):
    """
    Class extends marshmallow standart DateTime with "timestamp" format.
    """

    SERIALIZATION_FUNCS = DateTime.SERIALIZATION_FUNCS.copy()
    DESERIALIZATION_FUNCS = DateTime.DESERIALIZATION_FUNCS.copy()

    SERIALIZATION_FUNCS['timestamp'] = lambda x: x.timestamp()
    DESERIALIZATION_FUNCS['timestamp'] = datetime.fromtimestamp
    DEFAULT_FORMAT = 'timestamp'


class BytesField(Field):
    def _validate(self, value):
        super()._validate(value)
        if not isinstance(value, bytes):
            raise ValidationError('Invalid input type.')

        if value is None or value == b'':
            raise ValidationError('Invalid input type.')
