import logging
from logging import Logger
from typing import Optional

from aiohttp.web import Response, View
from aiojobs.aiohttp import spawn
from marshmallow.exceptions import ValidationError

from app.config import DEBUGLEVEL
from app.exceptions.tg_api import UpdateValidationError
from app.serializers.telegram import Update
from app.utils import is_start_message

log: Logger = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class WebhookHandler(View):
    """
    Webhook-хэндлер бота. Принимает входящее от Telegram API сообщение (update).
    Сериализует его, запускает бэкграунд корутину (asyncio job) который принимает решение о дальнейшем действии бота,
    и возвращает Response() не дожидаясь выполнения джоба. Вся дальнейшая работа бота происходит в фоновом джобе.
    Dispatch-джоб устанавливает lock в redis для этого пользователя и снимает его по завершении.
    Т.о. все входящие сообщения от этого пользователя во время действия lock отвергаются хэндлером.
    """
    @staticmethod
    def validate_user(update_data: dict) -> int:
        """
        Успешная сериализация update в теории может не иметь информации об отправителе сообщения. Поэтому тут происходит
        поиск и валидация информации об отправителе сообщения в пришедшем от Telegram объекте update.
        Возвращает telegram user id отправителя.
        """
        message: Optional[dict] = None
        from_obj: Optional[dict] = None
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

        log.debug(f"User validated: {from_obj}")
        return from_obj['id']

    @staticmethod
    def find_sender(data: dict) -> Optional[int]:
        """Используется для нахождения отправителя в случае ошибки сериализации."""
        # TODO: отрефакторить и объединить с validate_user
        if data.get('callback_query'):
            data: dict = data['callback_query']

        if data.get('message'):
            if data['message'].get('from'):
                if data['message']['from'].get('id'):
                    return data['message']['from']['id']

    async def post(self) -> Response:
        """
        POST-хэндлер webhook бота.
        Отвечает по URL, который устанавливается как webhook URL боту при старте Aiohttp Application.
        """
        data: dict = await self.request.json()

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

        user_id: int = self.validate_user(update)

        log.debug(f'Incoming message from {user_id}: {update}\n')

        with await self.request.app['redis'] as conn:
            if is_start_message(update):
                await conn.delete(f'{user_id}-lock')
            elif await conn.exists(f'{user_id}-lock'):
                await self.request.app['tg_api'].send_message(user_id, 'operation is pending')
                return Response()

        await spawn(self.request, self.request.app['dispatcher'].dispatch(user_id, update))

        return Response()
