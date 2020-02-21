from dataclasses import asdict
import logging
from logging import Logger
import pickle
from typing import Any, Dict, List, Optional, Tuple, Union

from aioredis.commands import Redis

from app.actions_dict import actions
from app.config import DEBUGLEVEL, OPERATION_LOCK_TIMEOUT, SIZE_1MB, USAGE_INFO
from app.exceptions.base import (
    ParametersValidationError,
    RoutingError,
    SoundHoundError,
)
from app.mediahandler import AudioHandler, VideoHandler
from app.serializers.telegram import (
    Animation,
    Audio,
    Document,
    PhotoSize,
    Video,
    Voice,
)
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
        self.video = VideoHandler()

    async def dispatch(self, user_id: int, update: dict):
        with await self.redis as redis_conn:
            # Потому что у aioredis нет lock
            await redis_conn.set(f'{user_id}-lock', '1', expire=OPERATION_LOCK_TIMEOUT)
            try:
                await self._dispatch(user_id, update)
            except SoundHoundError as exc:
                log.error('Internal exception caught')
                await self._handle_error(user_id, exc)
            except Exception as exc:
                log.error('Generic exception caught')
                await self._handle_error(user_id, exc)
            finally:
                await redis_conn.delete(f'{user_id}-lock')
                log.debug(f'Message from user {user_id} handled')
                log.debug(await self._get_state(user_id))

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
            valid_time_range: Tuple[int, int]

            # Если в любом месте начатого диалога нажали кнопку из стартового меню: начать кликнутый таск заново.
            if update.get('callback_query'):
                callback = update['callback_query'].get('data')
                if callback in [action for action in actions.action_map]:
                    await self._clean_state(user_id)
                    user_state.action = callback
                    await self._save_state(user_id, user_state)
                    await self.tg_api.send_message(user_id, f'Restarted: {actions.action_map[callback].title}')
                    await self._ask_action_parameters(user_id, callback)
                    return

            if action in ('crop', 'makevoice'):
                if not user_state.time_range:
                    time_range: str = self._get_tg_object(update, 'text')
                    user_state.time_range = self._validate_time_range(
                        time_range,
                        allow_empty=True if action == 'makevoice' else False,
                    )
                    await self._save_state(user_id, user_state)
                    await self.tg_api.send_message(user_id, 'Time range set, send audio file, please.')
                else:
                    audio_meta: dict = self._get_tg_object(update, 'audio')
                    log.info(f'Pre audio file meta: {audio_meta}')
                    valid_time_range = self._validate_file_duration(
                        audio_meta.get('duration'),
                        user_state.time_range,
                        600,
                    )
                    audio_meta['duration'] = self._get_new_file_duration(valid_time_range)

                    file, file_meta = await self.tg_api.download_file(audio_meta, 'audio')
                    audio_meta['suffix'] = file_meta['suffix']

                    mod_file: bytes = await self.audio.handle_file(
                        file,
                        audio_meta,
                        action,
                        valid_time_range,
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
                audio_meta['suffix'] = file_meta['suffix']
                opus_file: bytes = await self.audio.handle_file(file, audio_meta, action, user_state.time_range)
                audio_meta['mime_type'] = 'audio/x-opus+ogg'
                audio_meta['suffix'] = '.oga'
                await self.tg_api.upload_file(user_id, opus_file, audio_meta, False)
                await self.tg_api.send_message(user_id, 'Send next audio file or /start to start new action.')
            if action == 'makerounded':
                if not user_state.time_range:
                    time_range: str = self._get_tg_object(update, 'text')
                    user_state.time_range = self._validate_time_range(time_range, True, 60)
                    await self._save_state(user_id, user_state)
                    await self.tg_api.send_message(user_id, 'Time range set, send video file, please.')
                else:
                    video_meta: dict = self._get_tg_object(update, 'video')
                    log.info(f'Pre meta: {video_meta}')
                    # Проверим соответствие time_range и file duration если telegram уже знает о duration файла.
                    if video_meta.get('duration'):
                        _ = self._validate_file_duration(
                            video_meta['duration'],
                            user_state.time_range,
                            60,
                        )
                    file, file_meta = await self.tg_api.download_file(video_meta, 'video')
                    video_meta['suffix'] = file_meta['suffix']

                    video_meta = await self._collect_video_meta(video_meta, file)
                    valid_time_range = self._validate_file_duration(video_meta['duration'], user_state.time_range, 60)

                    new_duration = self._get_new_file_duration(valid_time_range)
                    rounded_video, radius = await self.video.make_rounded(file, video_meta, valid_time_range)

                    await self.tg_api.upload_roundy(user_id, rounded_video, new_duration, radius)
                    await self.tg_api.send_message(user_id, 'Send next video file or /start to start new action.')

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

    async def _collect_video_meta(self, video_meta: dict, content: bytes):
        """Если в meta для video не все параметры - получает их через ffprobe и дополняет meta."""
        height: int = video_meta.get('height', 0)
        width: int = video_meta.get('width', 0)
        duration: int = video_meta.get('duration', 0)
        if not all((height, width, duration)):
            log.warning('Video meta data is insufficient. Will try to obtain it from raw data with ffprobe.')
            meta: Dict[str, Any] = await self.video.get_video_meta(content, ('duration', 'height', 'width'))
            video_meta['height'] = meta.get('height', 0)
            video_meta['width'] = meta.get('width', 0)
            video_meta['duration'] = meta.get('duration', 0)

        return video_meta

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

    def _get_tg_object(self, update: Dict[str, Any], obj_type: str) -> Union[dict, str]:
        """
        Получает и валидирует объект text, photo, audio/voice/document или video/animation/document.
        Удостоверяется что есть метаданные для объекта, в случаях когда они нужны.
        Непосредственная скачка файла начнется позже если этот метод вернет нужный объект.
        """
        expected_media: str = 'text'
        expected_mimes: Dict[str, str] = {}
        if obj_type == 'audio':
            expected_media: str = 'audio/voice'
            expected_mimes = self.tg_api.audio_suffix_mimetype_map
        if obj_type == 'video':
            expected_media: str = 'video/animation'
            expected_mimes = self.tg_api.video_suffix_mimetype_map

        parse_error_text: str = f'Unable to parse {expected_media} object.'
        message: Dict[Any, Any] = update.get('message')
        data: Union[dict, str] = {}
        if not message:
            raise RoutingError('Unexpected message type. Expecting video/animation message.', update)

        if obj_type == 'text':
            if 'text' in message:
                return message.get('text', '')
            raise RoutingError(f'Unexpected message type. Expecting {expected_media} message.', message)

        if obj_type == 'photo':
            if 'photo' in message:
                try:
                    data = PhotoSize().dump(message['photo'].pop())
                    return data
                except Exception as exc:
                    raise ParametersValidationError('Unable to parse photo object.', update['message'], exc)

        if obj_type == 'audio':
            if 'audio' in message:
                try:
                    data = Audio().dump(message['audio'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)
            elif 'voice' in message:
                try:
                    data = Voice().dump(message['voice'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)
            elif 'document' in message:
                try:
                    data = Document().dump(message['document'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)

        if obj_type == 'video':
            if 'video' in message:
                try:
                    data = Video().dump(message['video'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)
            elif 'animation' in message:
                try:
                    data = Animation().dump(message['animation'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)
            elif 'document' in message:
                try:
                    data = Document().dump(message['document'])
                except Exception as exc:
                    raise ParametersValidationError(parse_error_text, message, exc)

        if not data:
            raise RoutingError(f'Unexpected message type. Expecting {expected_media} message.', message)

        mime: str = data.get('mime_type')
        if not mime or mime not in expected_mimes:
            raise RoutingError(f'Mime type: {mime} is not supported. Expecting {expected_media} message.', message)

        return data

    @staticmethod
    def _validate_time_range(
            data: str,
            allow_empty: Optional[bool] = False,
            max_limit: Optional[int] = 600,
    ) -> Tuple[int, int]:
        """
        Парсит присланный от пользователя в качестве range для crop текст.
        Проверяет что он является правильным range.
        Возвращает start_sec и end_sec провалидированного range.
        Если allow_empty - True и отсутствует data, то возвращается range: (0, 0),
        что вызовет рассчет time_range по duration файла позже.
        """
        if not data or data == '0':
            if allow_empty:
                return 0, 0
            raise ParametersValidationError('This operation needs a time range.', data)
        try:
            start_sec, end_sec = tuple(int(x.strip()) for x in data.split('-'))
        except Exception as exc:
            raise ParametersValidationError('Range is invalid.', data, exc)

        if start_sec >= end_sec:
            raise ParametersValidationError('First argument must be less than second.', data)

        if end_sec - start_sec >= max_limit:
            raise ParametersValidationError(f'Range exceeds max limit: {max_limit} seconds.', data)

        return start_sec, end_sec

    @staticmethod
    def _validate_file_duration(file_duration: int, time_range: Tuple[int, int], limit: int) -> Tuple[int, int]:
        """
        Проверяет duration входящего Audio/Voice на соответствие указанного для crop duration.
        В случаях когда аудио пришло как Document, duration отсутствует. Тогда пропускаем проверку.
        """
        if not file_duration:
            log.debug('No duration for incoming audio. Skip duration check.')
            return

        # Особый случай: range не был указан. Задать range по duration если он меньше минуты или минуту.
        if time_range == (0, 0):
            if file_duration <= limit:
                return 0, file_duration
            else:
                return 0, limit

        if time_range[1] > file_duration:
            raise ParametersValidationError(
                f'File duration ({file_duration}) mismatch time range {time_range}.',
                {
                    'duration': file_duration,
                    'range': time_range,
                }
            )

        return time_range

    @staticmethod
    def _get_new_file_duration(time_range: Tuple[int, int]) -> int:
        """
        Вычисляет будущий duration у файла после того как он будет обрезан согласно time_range.
        Нужно для указания нового duration при передаче файла серверам Telegram.
        Когда вызывается этот метод, time range уже должен быть вычислен даже если не был передан.
        """
        return time_range[1] - time_range[0]

    async def _handle_error(self, user_id: int, exc: Union[SoundHoundError, Exception]):
        """В случае SoundHound exception - отправляет юзеру в телеграм обязательный err_msg из него."""
        if isinstance(exc, SoundHoundError):
            log.error(f'Error happened: {exc}, {exc.err_msg}, extra: {exc.extra}. Original exception:{exc.orig_exc}.')
            log.debug(f'Gonna send error to {user_id}.')
            await self.tg_api.send_message(user_id, exc.err_msg)
        elif isinstance(exc, Exception):
            log.exception(f'Generic exception happened: {exc}')
            await self.tg_api.send_message(user_id, 'Generic error.')
        log.debug('Error sent to user.')
