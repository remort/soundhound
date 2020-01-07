from concurrent.futures._base import CancelledError
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiohttp.formdata import FormData

from app.config import SERVER_NAME, TOKEN
from app.exceptions.api import (
    FileSizeError,
    TGApiError,
    TGNetworkError,
    WrongFileError,
)

log = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')

# TODO: проверить работу со всеми этими файлами
SUPPORTED_PICTURE_SUFFIXES = ('.jpg', '.jpeg', '.png')


class TelegramAPI:
    SIZE_1MB = 1048576
    SIZE_10MB = 10485760
    SIZE_50MB = 52428800

    def __init__(self, http_client_session: ClientSession):
        self.token: str = TOKEN
        self.api_url: str = f'https://api.telegram.org/bot{self.token}/'
        self.session: ClientSession = http_client_session
        self.webhook_url: str = f'https://{SERVER_NAME}/webhook/'
        self.audio_suffix_mimetype_map = {
            'audio/mpeg': '.mp3',
            'audio/x-opus+ogg': '.ogg',
            'audio/mp4': '.m4a',
            'audio/flac': '.flac',
        }
        # TODO: picture_suffix_mimetype_map

    async def _request(
            self,
            path: str,
            method: Optional[str] = 'get',
            params: Optional[Dict[str, Any]] = None,
            form_data: Optional[Dict[str, Any]] = None,
    ) -> dict:
        url: str = os.path.join(self.api_url, path)
        log.debug(f'Request to TG API: {url}, params: {params}')
        try:
            async with self.session.request(method=method, url=url, params=params, data=form_data) as response:
                try:
                    resp: dict = await response.json()
                except ContentTypeError:
                    raise TGApiError('Unable to parse response body', response)
        except (CancelledError, ClientConnectorError) as exc:
            raise TGNetworkError('Request to Telegram API failed due to network issues.', exc)
        except Exception as exc:
            raise TGNetworkError('Request to Telegram API failed.', exc)

        if not resp.get('ok'):
            raise TGApiError(f"Telegram API returned error: {resp['error_code']}: {resp['description']}.", resp)

        return resp['result']

    async def set_webhook(self) -> str:
        """Инициализация вебхука"""
        resp: dict = await self._request('getWebhookInfo')
        if resp.get('url') != self.webhook_url:
            await self._request('setWebhook', params={'url': self.webhook_url})
        return self.webhook_url

    @staticmethod
    def _inline_keyboard_from_buttons(buttons: Optional[List[Tuple[str]]]):
        if not buttons:
            return ''
        return json.dumps({
            'inline_keyboard': [[{"callback_data": k[0], "text": k[1]}] for k in buttons]
        })

    async def send_message(self, user_id: int, message: str, buttons: Optional[List[Tuple[str]]] = None) -> dict:
        return await self._request(
            'sendMessage',
            params={
                'chat_id': user_id,
                'text': message,
                'reply_markup': self._inline_keyboard_from_buttons(buttons),
                'parse_mode': 'Markdown',
            }
        )

    async def download_file(self, meta: dict, file_type: str) -> Tuple[object, dict]:
        file_meta: dict = await self._request('getFile', method='post', params={'file_id': meta['file_id']})

        file_path: str = file_meta.get('file_path')
        file_suffix: str = Path(file_path).suffix

        if not file_suffix:
            file_suffix: str = self.audio_suffix_mimetype_map.get(meta.get('mime_type'))
        if not file_suffix:
            raise TGApiError('File has neither suffix nor suitable mime type.', file_meta)

        file_meta['suffix'] = file_suffix.lower()

        supported_suffixes: Tuple[str] = \
            self.audio_suffix_mimetype_map.values() if file_type == 'audio' else SUPPORTED_PICTURE_SUFFIXES

        if file_meta['suffix'] not in supported_suffixes:
            raise WrongFileError(
                'Unsupported file type.',
                {
                    'file_suffix': file_meta['suffix'],
                    'supported_suffixes': supported_suffixes,
                }
            )

        url = os.path.join(f'https://api.telegram.org/file/bot{self.token}', file_path)
        file_object: object = NamedTemporaryFile(suffix=file_meta['suffix'])
        try:
            async with self.session.get(url) as response:
                file_object.file.write(await response.read())
        except Exception as exc:
            file_object.close()
            raise TGNetworkError('Receiving file content is failed.', file_meta, exc)

        return file_object

    async def upload_file(self, user_id: int, file: bytes, meta: dict, as_voice: bool) -> dict:
        path: str
        params: dict = {'chat_id': str(user_id), 'duration': str(meta['duration'])}
        if len(file) >= self.SIZE_50MB:
            raise FileSizeError(
                f'Uploading file size limit exceeded. Size: {len(file)}, limit: {self.SIZE_50MB}',
                {'size': len(file), 'limit': self.SIZE_50MB}
            )

        suffix = self.audio_suffix_mimetype_map[meta['mime_type']]
        performer: str = meta.get('performer', '')
        title: str = meta.get('title', '')
        file_id: str = meta.get('file_id', '')
        file_unique_id: str = meta.get('file_unique_id', '')

        log.info(meta)
        filename: str = f"{performer or file_id}-{title or file_unique_id}"
        form_data = FormData(quote_fields=False)
        if as_voice:
            path = 'sendVoice'
            form_data.add_field('voice', file, filename=f"{filename}.ogg", content_type='audio/ogg')
        else:
            path = 'sendAudio'
            params.update({'performer': performer, 'title': title})
            form_data.add_field('audio', file, filename=f"{filename}{suffix}", content_type=meta['mime_type'])

        return await self._request(path, params=params, form_data=form_data)

    async def clean(self):
        await self.session.close()
