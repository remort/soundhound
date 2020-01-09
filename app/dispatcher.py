import logging
from logging import Logger
import pickle
from typing import List, Tuple

from aioredis.commands import Redis

from app.actions_dict import actions
from app.audiohandler import AudioHandler
from app.config import DEBUGLEVEL, OPERATION_LOCK_TIMEOUT, USAGE_INFO
from app.exceptions.api import (
    NotImplementedYetError,
    ParametersValidationError,
    RoutingError,
    SoundHoundError,
)
from app.serializers.telegram import Audio
from app.serializers.user_state import UserStateModel, UserStateSchema
from app.tg_api import TelegramAPI

log: Logger = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class Dispatcher:
    def __init__(self, redis_conn, bot_api, client_session):
        self.redis: Redis = redis_conn
        self.tg_api: TelegramAPI = bot_api
        self.client_session = client_session
        self.audio = AudioHandler()

    async def dispatch(self, user_id, update):
        with await self.redis as redis_conn:
            # Потому что у aioredis нет lock
            await redis_conn.set(f'{user_id}-lock', '1', expire=OPERATION_LOCK_TIMEOUT)
            try:
                await self._dispatch(user_id, update)
            except SoundHoundError as exc:
                await self.handle_error(user_id, exc)
            except Exception as exc:
                log.exception('Generic exception happened')
            finally:
                await redis_conn.delete(f'{user_id}-lock')
                log.debug(f'Message from user {user_id} handled')

    async def initiate_task(self, user_id):
        await self._send_action_list(user_id)
        user_state = UserStateModel(id=user_id, actions_sent=True)
        await self._save_state(user_id, user_state)

    async def _dispatch(self, user_id, update):
        user_state: UserStateModel
        user_state = await self._get_state(user_id)

        message = update.get('message')
        if message:
            if message.get('text') in ('/start', '/reset'):
                log.debug(f'User {user_id} reset his task')
                await self._clean_state(user_id)
                await self.initiate_task(user_id)
                return
            if message.get('text') == '/info':
                await self.tg_api.send_message(user_id, USAGE_INFO)
                return

        if not user_state:
            await self.initiate_task(user_id)
            return

        if not user_state.actions_sent:
            log.error('State exists but action list was not send. Unknown message: ', update)

        if user_state.action:
            if user_state.action in ('crop', 'makevoice'):
                if not user_state.time_range:
                    user_state.time_range = self._validate_user_time_range(update)
                    await self._save_state(user_id, user_state)

                    if user_state.audio_file_sent:
                        raise RoutingError('Action and parameters set. Expecting audio but got message.', update)
                    await self.tg_api.send_message(user_id, 'Time range set, send audio file, please.')
                    return

                elif not user_state.audio_file_sent:
                    audio_meta: dict = self._validate_audio_file(update)
                    self._validate_file_duration(audio_meta['duration'], user_state.time_range)
                    audio_meta['duration'] = user_state.time_range[1] - user_state.time_range[0]

                    file: object = await self.tg_api.download_file(audio_meta, 'audio')

                    user_state.audio_meta = audio_meta
                    user_state.audio_file = file.name
                    await self._save_state(user_id, user_state)

                    mod_file: bytes = await self.audio.handle_file(file, user_state.action, user_state.time_range)

                    as_voice: bool = True if user_state.action == 'makevoice' else False
                    await self.tg_api.upload_file(user_id, mod_file, audio_meta, as_voice)

                    await self._clean_state(user_id)
                    return
        else:
            callback_query: dict = update.get('callback_query')
            if not callback_query:
                raise RoutingError('Button press expected', update)

            action = update['callback_query'].get('data')
            if not action:
                raise RoutingError('Unable to parse button press.', update)
            if action == 'set_cover':
                await self._clean_state(user_id)
                raise NotImplementedYetError

            user_state.action = action
            await self._save_state(user_id, user_state)
            await self._ask_action_parameters(user_id, action)

    async def _send_action_list(self, user_id: int):
        buttons: List[Tuple[str]] = [(action_name, action.title) for action_name, action in actions.action_map.items()]
        await self.tg_api.send_message(user_id, 'Please select an action', buttons)
        log.debug(f'Action list sent to {user_id}')

    async def _ask_action_parameters(self, user_id, action: str):
        action_message = actions.action_map[action].message
        await self.tg_api.send_message(user_id, action_message)
        log.debug(f'Parameters asked for {user_id}')

    async def _get_state(self, user_id) -> UserStateModel:
        with await self.redis as redis_conn:
            if not await redis_conn.exists(f'{user_id}-state'):
                return None

            return UserStateSchema().loads(
                pickle.loads(
                    await redis_conn.get(f'{user_id}-state')
                )
            )

    async def _save_state(self, user_id, user_state: UserStateModel):
        with await self.redis as redis_conn:
            log.info(f'serialized state: {UserStateSchema().dumps(user_state)}')

            res = await redis_conn.set(
                f'{user_id}-state',
                pickle.dumps(
                    UserStateSchema().dumps(user_state)
                )
            )
            log.debug(f'Saving state result: {res}')

    async def _clean_state(self, user_id):
        with await self.redis as redis_conn:
            res = await redis_conn.delete(f'{user_id}-state')
            log.debug(f'Cleaning state result: {res}')

    @staticmethod
    def _validate_audio_file(update: dict) -> dict:
        if not update.get('message'):
            raise RoutingError('Unexpected message type. Expecting audio message.', update)
        if not update['message'].get('audio'):
            raise RoutingError('No audio found in message. Expecting audio message.', update)

        try:
            audio_metadata = Audio().dump(update['message']['audio'])
        except Exception as exc:
            raise ParametersValidationError('Unable to parse audio object.', update['message'], exc)

        return audio_metadata

    @staticmethod
    def _validate_file_duration(file_duration: int, time_range: Tuple[int, int]):
        time_range: int = time_range[1] - time_range[0]
        if time_range >= file_duration:
            raise ParametersValidationError(
                f'File duration ({file_duration}) less than or equal time range ({time_range}).',
                {
                    'duration': file_duration,
                    'range': time_range,
                }
            )

    @staticmethod
    def _validate_user_time_range(update: dict):
        message = update.get('message')

        if not message:
            raise RoutingError('Unexpected message type. Expecting text message.', update)

        if not message.get('text'):
            raise RoutingError('Unable to parse message: no "text" field found.', update)

        data = message['text']

        if not data:
            raise ParametersValidationError('Unable to parse range.', {'message': update['message']})

        try:
            start_sec, end_sec = tuple(int(x.strip()) for x in data.split('-'))
        except Exception as exc:
            raise ParametersValidationError('Range is invalid.', data, exc)

        if start_sec >= end_sec:
            raise ParametersValidationError('First argument must be less than second.', data)

        return start_sec, end_sec

    async def handle_error(self, user_id, exc):
        error_desc: str = None
        extra: str = None
        message: str = f'{exc.err_msg}'

        # if exc.extra:
        #     extra = '\n'.join([f'{key}: {val}' for key, val in exc.extra.items()])
        #     message += f'\n{extra}'
        #
        # if exc.orig_exc:
        #     log.debug(exc.orig_exc)
        #     error_desc = exc.orig_exc.message
        #     message += f'\n{error_desc}'

        await self.tg_api.send_message(user_id, message)
        log.debug(f'Error message sent: {message}')
