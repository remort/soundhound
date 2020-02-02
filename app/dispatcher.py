from dataclasses import asdict
import logging
from logging import Logger
import pickle
from typing import List, Optional, Tuple, Union

from aioredis.commands import Redis

from app.actions_dict import actions
from app.audiohandler import AudioHandler
from app.config import DEBUGLEVEL, OPERATION_LOCK_TIMEOUT, SIZE_1MB, USAGE_INFO
from app.exceptions.base import (
    ParametersValidationError,
    RoutingError,
    SoundHoundError,
)
from app.serializers.telegram import Audio, Document, PhotoSize, Schema, Voice
from app.serializers.user_state import UserStateModel, UserStateSchema
from app.tg_api import TelegramAPI
from app.utils import is_start_message, resize_thumbnail

log: Logger = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class Dispatcher:
    def __init__(self, redis_conn, bot_api, client_session):
        self.redis: Redis = redis_conn
        self.tg_api: TelegramAPI = bot_api
        self.client_session = client_session
        self.audio = AudioHandler()

    async def dispatch(self, user_id: int, update: dict):
        with await self.redis as redis_conn:
            # Потому что у aioredis нет lock
            await redis_conn.set(f'{user_id}-lock', '1', expire=OPERATION_LOCK_TIMEOUT)
            try:
                await self._dispatch(user_id, update)
            except SoundHoundError as exc:
                log.debug('Internal exception caught')
                await self._handle_error(user_id, exc)
            except Exception as exc:
                log.exception('Generic exception caught')
                await self._handle_error(user_id, exc)
            finally:
                await redis_conn.delete(f'{user_id}-lock')
                log.debug(f'Message from user {user_id} handled')

    async def initiate_task(self, user_id):
        await self._send_action_list(user_id)
        user_state = UserStateModel(id=user_id, actions_sent=True)
        await self._save_state(user_id, user_state)

    async def _dispatch(self, user_id: int, update: dict):
        """Роутинг мессаджей юзера происходит тут."""
        message = update.get('message')
        if message:
            if is_start_message(update):
                log.debug(f'User {user_id} sent /start. Reset his task.')
                await self._clean_state(user_id)
                await self.initiate_task(user_id)
                return
            if message.get('text') == '/info':
                await self.tg_api.send_message(user_id, USAGE_INFO)
                return

        user_state: UserStateModel
        user_state = await self._get_state(user_id)

        if not user_state:
            await self.initiate_task(user_id)
            return

        if not user_state.actions_sent:
            log.error('State exists but action list was not send. Unknown message: ', update)

        if user_state.action:
            file: bytes
            file_meta: dict
            action: str = user_state.action

            if action in ('crop', 'makevoice'):
                if not user_state.time_range:
                    time_range: str = self._get_tg_object(update, 'text')
                    user_state.time_range = self._validate_time_range(time_range)
                    await self._save_state(user_id, user_state)
                    await self.tg_api.send_message(user_id, 'Time range set, send audio file, please.')
                else:
                    audio_meta: dict = self._get_tg_object(update, 'audio')
                    self._validate_file_duration(audio_meta.get('duration'), user_state.time_range)
                    audio_meta['duration'] = user_state.time_range[1] - user_state.time_range[0]

                    file, file_meta = await self.tg_api.download_file(audio_meta, 'audio')

                    user_state.audio_meta = audio_meta
                    await self._save_state(user_id, user_state)

                    mod_file: bytes = await self.audio.handle_file(
                        file,
                        file_meta,
                        action,
                        user_state.time_range,
                    )

                    as_voice: bool = True if action == 'makevoice' else False
                    await self.tg_api.upload_file(user_id, mod_file, audio_meta, as_voice)
                    await self.tg_api.send_message(user_id, 'Send next audio file or /start to start new action.')
            if action in ('thumbnail', 'setcover'):
                if not user_state.thumbnail_file:
                    photo_meta: dict = self._get_tg_object(update, 'photo')

                    if not 0 < photo_meta['file_size'] < SIZE_1MB:
                        raise ParametersValidationError('Telegram photo is empty or too large.', photo_meta)

                    file, meta = await self.tg_api.download_file(photo_meta, 'photo')
                    user_state.thumbnail_file = file
                    user_state.tg_thumbnail_file = resize_thumbnail(file, photo_meta['width'], photo_meta['height'])
                    await self._save_state(user_id, user_state)
                    await self.tg_api.send_message(user_id, 'Got thumbnail, send audio file, please.')
                else:
                    audio_meta: dict = self._get_tg_object(update, 'audio')

                    file, file_meta = await self.tg_api.download_file(audio_meta, 'audio')
                    if action == 'setcover':
                        file = await self.audio.handle_file(
                            file,
                            file_meta,
                            action,
                            None,
                            user_state.thumbnail_file,
                        )
                    await self.tg_api.upload_file(user_id, file, audio_meta, False, user_state.tg_thumbnail_file)
                    await self.tg_api.send_message(user_id, 'Send next audio file or /start to start new action.')
            if action == 'makeopus':
                audio_meta: dict = self._get_tg_object(update, 'audio')
                file, file_meta = await self.tg_api.download_file(audio_meta, 'audio')
                audio_meta['suffix'] = file_meta.get('suffix')
                opus_file: bytes = await self.audio.handle_file(
                    file,
                    audio_meta,
                    action,
                    user_state.time_range,
                )
                audio_meta['mime_type'] = 'audio/x-opus+ogg'
                audio_meta['suffix'] = '.oga'
                await self.tg_api.upload_file(user_id, opus_file, audio_meta, False)
                await self.tg_api.send_message(user_id, 'Send next audio file or /start to start new action.')

        else:
            callback_query: dict = update.get('callback_query')
            if not callback_query:
                raise RoutingError('Button press expected', update)

            new_action = update['callback_query'].get('data')
            if not new_action:
                raise RoutingError('Unable to parse button press.', update)

            user_state.action = new_action
            await self._save_state(user_id, user_state)
            await self._ask_action_parameters(user_id, new_action)

    async def _send_action_list(self, user_id: int):
        """Начало диалога с юзером. Выслать action list-клавиатуру."""
        buttons: List[Tuple[str]] = [(action_name, action.title) for action_name, action in actions.action_map.items()]
        await self.tg_api.send_message(user_id, 'Please select an action', buttons)
        log.debug(f'Action list sent to {user_id}')

    async def _ask_action_parameters(self, user_id, action: str):
        """Второй шаг диалога с юзером. Запрос параметров после выбора действия."""
        action_message = actions.action_map[action].message
        await self.tg_api.send_message(user_id, action_message)
        log.debug(f'Parameters asked for {user_id}')

    async def _get_state(self, user_id: int) -> UserStateModel:
        """
        Получаем стейт юзера по его id из redis в виде байт.
        Десериализуем pickle. Затем сериализуем в python объект через сериализатор Marshmallow,
        затем в объект модели UserStateModel.
        """
        with await self.redis as redis_conn:
            binary_data: Optional[bytes] = await redis_conn.get(f'{user_id}-state')
            if not binary_data:
                return None

            return UserStateModel(**UserStateSchema().load(pickle.loads(binary_data)))

    async def _save_state(self, user_id: int, user_state: UserStateModel):
        """
        Входящая модель UserStateModel (dataclass объект) хранит разные поля, в том числе байтовые.
        Проверяем верность модели сериализуя ее с помощью UserStateSchema в питонный объект.
        В байты, для хранения в redis, сериализуем с помощью pickle, т.к. в JSON нельзя из-за байт.
        """
        with await self.redis as redis_conn:
            await redis_conn.set(f'{user_id}-state', pickle.dumps(UserStateSchema().load(asdict(user_state))))

    async def _clean_state(self, user_id: int):
        with await self.redis as redis_conn:
            await redis_conn.delete(f'{user_id}-state')
        log.debug(f'State for {user_id} is cleaned.')

    def _get_tg_object(self, update: dict, obj_type: str) -> Union[dict, str]:
        """
        Из входящего update от пользователя берет obj_type (аудио, картинка, текст) или выбрасывает исключение.
        """
        data: Union[dict, str] = None
        if not update.get('message'):
            raise RoutingError('Unexpected message type. Expecting audio message.', update)

        # Если мы ожидаем Audio а пришел не он, то это может быть Voice или Document с валидным аудио по mime.
        if obj_type == 'audio' and not update['message'].get(obj_type):
            payload: dict = update['message'].get('voice')
            serializer: Schema = Voice()
            if not payload:
                payload = update['message'].get('document')
                if not payload:
                    raise RoutingError(f'No document found in message. Expecting "{obj_type}/voice" message.', update)
                serializer = Document()

            try:
                data = serializer.dump(payload)
            except Exception as exc:
                raise ParametersValidationError('Unable to parse object.', update['message'], exc)

            mime: str = data.get('mime_type')
            if not mime or mime not in self.tg_api.audio_suffix_mimetype_map:
                raise RoutingError(f'Mime type: {mime} is not supported. Expecting "{obj_type}" message.', update)

            return data
        elif not update['message'].get(obj_type):
            raise ParametersValidationError(f'Expecting {obj_type} message.', update['message'])

        if obj_type == 'audio':
            try:
                data = Audio().dump(update['message']['audio'])
            except Exception as exc:
                raise ParametersValidationError('Unable to parse audio object.', update['message'], exc)

        if obj_type == 'photo':
            try:
                data = PhotoSize().dump(update['message']['photo'].pop())
            except Exception as exc:
                raise ParametersValidationError('Unable to parse photo object.', update['message'], exc)

        if obj_type == 'text':
            data = update['message'].get('text')

            if not data:
                raise ParametersValidationError('Expecting text.', {'message': update['message']})

        return data

    @staticmethod
    def _validate_time_range(data: str) -> Tuple[int, int]:
        """
        Парсит присланный от пользователя в качестве range для crop текст.
        Проверяет что он является правильным range.
        Возвращает start_sec и end_sec провалидированного range.
        """
        try:
            start_sec, end_sec = tuple(int(x.strip()) for x in data.split('-'))
        except Exception as exc:
            raise ParametersValidationError('Range is invalid.', data, exc)

        if start_sec >= end_sec:
            raise ParametersValidationError('First argument must be less than second.', data)

        return start_sec, end_sec

    @staticmethod
    def _validate_file_duration(file_duration: int, time_range: Tuple[int, int]):
        """
        Проверяет duration входящего Audio/Voice на соответствие указанного для crop duration.
        В случаях когда аудио пришло как Document, duration отсутствует. Тогда пропускаем проверку.
        """
        if not file_duration:
            log.debug('No duration for incoming audio. Skip duration check.')
            return

        if time_range[1] >= file_duration:
            raise ParametersValidationError(
                f'File duration ({file_duration}) mismatch time range ({time_range}).',
                {
                    'duration': file_duration,
                    'range': time_range,
                }
            )

    async def _handle_error(self, user_id: int, exc: Union[SoundHoundError, Exception]):
        """В случае SoundHound exception - отправляет юзеру в телеграм обязательный err_msg из него."""
        if isinstance(exc, SoundHoundError):
            log.debug(f'Error happened: {exc}, {exc.err_msg}, extra: {exc.extra}. Original exception:{exc.orig_exc}.')
            log.debug(f'Gonna send error to {user_id}.')
            await self.tg_api.send_message(user_id, exc.err_msg)
        elif isinstance(exc, Exception):
            log.debug(f'Generic exception happened: {exc}')
            await self.tg_api.send_message(user_id, 'Generic error.')
        log.debug('Error sent to user.')
