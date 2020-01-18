import asyncio
import logging
import sys
from logging import Logger

from aiohttp import ClientSession
from aiohttp.web import Application, AppRunner, TCPSite
from aiojobs.aiohttp import setup
import aioredis
from aioredis.commands import Redis

from app.config import DEBUGLEVEL
from app.dispatcher import Dispatcher
from app.exceptions.base import SoundHoundError
from app.tg_api import TelegramAPI
from app.webhook import WebhookHandler

log: Logger = logging.getLogger(__name__)
logging.basicConfig(level=DEBUGLEVEL)


async def init_webhook(app):
    try:
        webhook: str = await app['tg_api'].set_webhook()
        log.debug(f'Webhook set to {webhook}')
    except SoundHoundError as err:
        log.error(f'Webhook set failed. Error: {err.err_msg}')
        sys.exit(4)


async def close_redis(app):
    app['redis'].close()
    await app['redis'].wait_closed()
    log.debug('Redis is closed')


async def close_client_session(app):
    await app['http_client_session'].close()
    log.debug('Client sessions is closed')


async def http_app_factory() -> Application:
    """Создает, настраивает и возвращает Application-объект для запуска в контейнере через gunicorn."""
    redis_pool: Redis = await aioredis.create_redis_pool(
        ('redis', 6379), db=0,
    )
    app: Application = Application()

    app['redis'] = redis_pool
    app['http_client_session'] = ClientSession(conn_timeout=180, read_timeout=180, trust_env=True)
    app['tg_api']: TelegramAPI = TelegramAPI(app['http_client_session'])
    app['dispatcher'] = Dispatcher(app['redis'], app['tg_api'], app['http_client_session'])

    app.router.add_route('POST', '/webhook/', WebhookHandler)
    setup(app)
    app.on_startup.append(init_webhook)
    app.on_cleanup.append(close_client_session)
    app.on_shutdown.append(close_redis)

    return app


async def run_server():
    """Для запуска вне контейнера."""
    app: Application = await http_app_factory()
    runner: AppRunner = AppRunner(app)
    await runner.setup()
    site: TCPSite = TCPSite(runner, 'localhost', 8080)
    await site.start()
    await runner.cleanup()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_server())
    except KeyboardInterrupt:
        pass
    loop.close()
