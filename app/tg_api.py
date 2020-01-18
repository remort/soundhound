from concurrent.futures._base import CancelledError
import json
import logging
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Tuple, Union

from aiohttp import ClientConnectorError, ClientSession, ContentTypeError
from aiohttp.formdata import FormData

from app.config import (
    DEBUGLEVEL,
    SERVER_NAME,
    PUBLIC_PORT,
    SIZE_1MB,
    SIZE_10MB,
    SIZE_50MB,
    TOKEN,
)
from app.exceptions.api import (
    FileSizeError,
    TGApiError,
    TGNetworkError,
    WrongFileError,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


class TelegramAPI:
    def __init__(self, http_client_session: ClientSession):
        self.token: str = TOKEN
        self.api_url: str = f'https://api.telegram.org/bot{self.token}/'
        self.session: ClientSession = http_client_session
        self.webhook_url: str = f'https://{SERVER_NAME}:{PUBLIC_PORT}/webhook/'
        self.audio_suffix_mimetype_map = {
            'audio/mpeg': '.mp3',
            'audio/x-opus+ogg': '.ogg',
            'audio/mp4': '.m4a',
            'audio/flac': '.flac',
        }
        self.picture_suffix_mimetype_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
        }

    async def _request(
            self,
            path: str,
            method: Optional[str] = 'get',
            params: Optional[Dict[str, Any]] = None,
            form_data: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Внутренний метод реализующий запрос к Telegram API. Другие методы используют его. Кроме зарузки файла."""
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
            log.error(f"Telegram API returned error: {resp['error_code']}: {resp['description']}.")
            raise TGApiError(f"Telegram API returned error: {resp['error_code']}: {resp['description']}.", resp)

        return resp['result']

    async def set_webhook(self) -> str:
        """
        Инициализация вебхука.
        Telegram: Webhook can be set up only on ports 80, 88, 443 or 8443
        """

        resp: dict = await self._request('getWebhookInfo')
        if resp.get('url') != self.webhook_url:
            await self._request('setWebhook', params={'url': self.webhook_url})
        return self.webhook_url

    @staticmethod
    def _inline_keyboard_from_buttons(buttons: Optional[List[Tuple[str]]]):
        """Принимает list tuple объектов ('id кнопки', 'title кнопки') и возвращает Telegram Inline Keyboard из них."""
        if not buttons:
            return ''
        return json.dumps({
            'inline_keyboard': [[{"callback_data": k[0], "text": k[1]}] for k in buttons]
        })

    async def send_message(self, user_id: int, message: str, buttons: Optional[List[Tuple[str]]] = None) -> dict:
        """Публичный метод отправки текстового сообщения пользователю."""
        return await self._request(
            'sendMessage',
            params={
                'chat_id': user_id,
                'text': message,
                'reply_markup': self._inline_keyboard_from_buttons(buttons),
                'parse_mode': 'Markdown',
            }
        )

    async def download_file(
            self,
            meta: dict,
            file_type: str,
            as_bytes: bool = False,
    ) -> Tuple[Union[object, bytes], dict]:
        """Публичный метод получения файла с серверов Telegram."""
        file_meta: dict = await self._request('getFile', method='post', params={'file_id': meta['file_id']})
        file_path: str = file_meta.get('file_path')
        file_suffix: str = Path(file_path).suffix.lower()
        log.debug(file_suffix)

        if not file_suffix:
            file_suffix = self.audio_suffix_mimetype_map.get(meta.get('mime_type'))
        if not file_suffix:
            raise TGApiError('File has neither suffix nor suitable mime type.', file_meta)

        file_meta['suffix'] = file_suffix

        supported_suffixes: Tuple[str] = ()
        if file_type == 'audio':
            supported_suffixes = self.audio_suffix_mimetype_map.values()
        if file_type == 'photo':
            supported_suffixes = self.picture_suffix_mimetype_map.values()

        if file_meta['suffix'] not in supported_suffixes:
            raise WrongFileError(
                'Unsupported file type.',
                {
                    'file_suffix': file_meta['suffix'],
                    'supported_suffixes': supported_suffixes,
                }
            )

        url: str = os.path.join(f'https://api.telegram.org/file/bot{self.token}', file_path)
        file_object: object = NamedTemporaryFile(suffix=file_meta['suffix'])
        try:
            async with self.session.get(url) as response:
                file_object.file.write(await response.read())
        except Exception as exc:
            file_object.close()
            raise TGNetworkError('Receiving file content is failed.', file_meta, exc)

        if as_bytes:
            file_object.seek(0)
            return file_object.read(), file_meta

        return file_object, file_meta

    async def upload_file(
            self,
            user_id: int,
            file_content: bytes,
            file_meta: dict,
            as_voice: bool,
            thumbnail: bytes = None,
    ) -> dict:
        """
        Публичный метод загрузки файла на сервера Telegram.
        Thumbnail: Шлется только байтами, только если аудиофайл так же шлется байтами, только для метода sendAudio.
        """
        path: str
        params: dict = {'chat_id': str(user_id), 'duration': str(file_meta['duration'])}
        # TODO: кажется на самом деле свыше около 20 МБ телеграм уже не принимает.
        if len(file_content) >= SIZE_50MB:
            raise FileSizeError(
                f'Uploading file size limit exceeded. Size: {len(file_content)}, limit: {SIZE_50MB}',
                {'size': len(file_content), 'limit': SIZE_50MB}
            )

        suffix: str = self.audio_suffix_mimetype_map[file_meta['mime_type']]
        performer: str = file_meta.get('performer', '')
        title: str = file_meta.get('title', '')
        file_id: str = file_meta.get('file_id', '')
        file_unique_id: str = file_meta.get('file_unique_id', '')

        filename: str = f"{performer or file_id}-{title or file_unique_id}"
        form_data: FormData = FormData(quote_fields=False)
        if as_voice:
            path = 'sendVoice'
            form_data.add_field('voice', file_content, filename=f"{filename}.ogg", content_type='audio/ogg')
            if thumbnail:
                log.error('Thumbnails allowed for sendAudio only.')
        else:
            path = 'sendAudio'
            params.update({'performer': performer, 'title': title})
            form_data.add_field(
                'audio',
                file_content,
                filename=f"{filename}{suffix}",
                content_type=file_meta['mime_type']
            )
            if thumbnail:
                form_data.add_field('thumb', thumbnail, filename=f"thumb.jpeg", content_type='image/jpeg')

        return await self._request(path, params=params, form_data=form_data)
