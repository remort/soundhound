import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from aiohttp import ClientSession, FormData

from actions_dict import actions

log = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')

PROXY = os.getenv('PROXY', 'http://172.19.0.2:8118')
SUPPORTED_AUDIO_SUFFIXES = ('.mp3', '.wav', '.ogg')
SUPPORTED_PICTURE_SUFFIXES = ('.jpg', '.jpeg', '.png')


class BotHandler:
    SIZE_1MB = 1048576
    SIZE_10MB = 10485760
    SIZE_50MB = 52428800

    def __init__(self):
        self.token = os.getenv('TOKEN')
        self.api_url = f'https://api.telegram.org/bot{self.token}/'
        self.session = ClientSession(raise_for_status=False, read_timeout=180, conn_timeout=180, trust_env=True)

    async def http_request(self, url, method='get', params=None, data=None):
        async with self.session.request(method=method, url=url, params=params, data=data, proxy=PROXY) as response:
            resp = await response.json()
            if not resp.get('ok'):
                return False, resp
            return True, resp

    async def get_updates(self, offset=None):
        url = os.path.join(self.api_url, 'getUpdates')
        if offset:
            url = url + f'?offset={offset}'

        status, resp = await self.http_request(url)

        log.info('Updates fetched')
        return status, resp

    async def send_message(self, user_id, message):
        url = os.path.join(self.api_url, 'sendMessage')
        data = {
            "chat_id": user_id,
            "text": message,
        }
        status, resp = await self.http_request(url, params=data)

        log.info(f'Message "{message}" sent to {user_id}')
        return status, resp

    async def send_action_list(self, user_id):
        url = os.path.join(self.api_url, 'sendMessage')
        keyboard = json.dumps(
            {"inline_keyboard": [[{"callback_data": x, "text": actions[x]['title']}] for x in actions]})

        data = {
            "chat_id": user_id,
            "text": "Please select an action",
            "reply_markup": keyboard
        }
        status, resp = await self.http_request(url, params=data)

        log.info(f'Action list sent to {user_id}')
        return status, resp

    async def ask_action_parameters(self, sender, action):
        await self.send_message(sender, actions[action]['message'])

    async def download_file(self, file_id, sender, file_type):
        url = os.path.join(self.api_url, 'getFile')
        data = {"file_id": file_id}
        status, resp = await self.http_request(url, method='post', data=data)

        file_path = resp['result'].get('file_path')
        file_suffix = Path(file_path).suffix
        file_size = resp['result'].get('file_size')
        log.debug(f'File size is: {file_size}')

        supported_suffixes = SUPPORTED_AUDIO_SUFFIXES if file_type == 'audio' else SUPPORTED_PICTURE_SUFFIXES

        # TODO: обрабатывать что если файл без суффикса, проставлять суффикс по mimetype (брать из magic bits)
        if file_suffix not in supported_suffixes:
            await self.send_message(
                sender,
                f"Only {','.join(supported_suffixes)} are supported, filename is {file_path}"
            )
            return False

        # TODO формировать url через join из urllib
        # url = f'https://api.telegram.org/file/bot{self.token}/{file_path}'
        url = os.path.join(f'https://api.telegram.org/file/bot{self.token}', file_path)
        print(f'file url: {url}')

        # TODO: слать tg-message-крутилку тут что "подождите, идет загрузка"
        log.debug('start downloading file')
        try:
            audio_file = NamedTemporaryFile(suffix=file_suffix)
            async with self.session.get(url, proxy=PROXY) as response:
                # async for data, _ in response.content.iter_chunks():
                # async for line in response.read():
                audio_file.file.write(await response.read())
        except Exception as error:
            log.error('Unable to fetch file, close temp file')
            log.error(error)
            await self.send_message(sender, 'Unable to fetch file from telegram CDR, try later.')
            audio_file.close()
            return False

        log.debug('file is downloaded')
        return audio_file, file_suffix

    async def upload_file(self, sender, audio, as_voice, duration=0):
        with open('/tmp/b4send_for_test.mp3', 'wb') as file_with_thumbnail:
            file_with_thumbnail.write(audio)

        data = FormData()
        if not as_voice:
            assert len(audio) <= self.SIZE_50MB
            method = 'sendAudio'
            data = {'chat_id': str(sender), 'audio': audio, 'duration': str(duration)}
        if as_voice:
            assert len(audio) <= self.SIZE_1MB
            method = 'sendVoice'
            data = {'chat_id': str(sender), 'voice': audio, 'duration': str(duration)}

        url = os.path.join(self.api_url, method)
        status, resp = await self.http_request(url, data=data)

        return status, resp

    async def clean(self):
        await self.session.close()


bot = BotHandler()
