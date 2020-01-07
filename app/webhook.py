from aiojobs.aiohttp import spawn
import logging
from logging import Logger
from typing import Any, Dict

from aiohttp.web import View, json_response, Response
from marshmallow.exceptions import ValidationError

from app.exceptions.api import UpdateValidationError
from app.serializers.telegram import Update

log: Logger = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')


class WebhookHandler(View):
    @staticmethod
    def validate_update(update_data):
        message = None
        from_obj = None
        if update_data.get('message'):
            message = update_data.get('message')
            from_obj = message.get('from')
        elif update_data.get('callback_query'):
            from_obj = update_data['callback_query'].get('from')
            message = update_data['callback_query'].get('message')

        if not from_obj:
            raise UpdateValidationError('No "from" object found in request.', update_data)
        if not message:
            raise UpdateValidationError('No "message" object found in request.', update_data)

        if from_obj.get('is_bot'):
            raise UpdateValidationError('Bots are not allowed.', update_data)

        return from_obj['id']

    @staticmethod
    def find_sender(data):
        if data.get('callback_query'):
            data = data['callback_query']

        if data.get('message'):
            if data['message'].get('from'):
                if data['message']['from'].get('id'):
                    return data['message']['from']['id']

    async def post(self) -> json_response:
        data: Dict[Any, Any] = await self.request.json()

        if data.get('message'):
            log.debug('Incoming message')
        else:
            log.debug('Incoming callback query')

        try:
            update = Update().load(data)
        except ValidationError:
            user_id = self.find_sender(data)
            if user_id:
                await self.request.app['tg_api'].send_message(
                    user_id,
                    'Unknown message type. Only audio/Voice, text and keyboard messages are supported by now.',
                )
            log.exception('Marshmallow serialization failed.')
            return Response()

        user_id = self.validate_update(update)

        log.debug(f'Incoming message from {user_id}')
        with await self.request.app['redis'] as conn:
            if await conn.exists(f'{user_id}-lock'):
                await self.request.app['tg_api'].send_message(user_id, 'operation is pending')
                return Response()

        await spawn(self.request, self.request.app['dispatcher'].dispatch(user_id, update))

        return Response()
