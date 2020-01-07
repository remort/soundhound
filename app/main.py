from aiojobs.aiohttp import setup, spawn
import asyncio
import logging
from logging import Logger

from aiohttp import ClientSession
from aiohttp.web import (
    Application,
    AppRunner,
    TCPSite,
)

import aioredis
from aioredis.commands import Redis

from app.dispatcher import Dispatcher
from app.tg_api import TelegramAPI
from app.webhook import WebhookHandler


log: Logger = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')


async def init_webhook(app):
    webhook: str = await app['tg_api'].set_webhook()
    log.debug(f'Webhook set to {webhook}')


async def close_redis(app):
    log.info('in redis shutdown')

    app['redis'].close()
    await app['redis'].wait_closed()
    log.debug('Redis is closed')


async def close_client_session(app):
    await app['http_client_session'].close()
    log.debug('Client sessions is closed')


async def http_app_factory() -> Application:
    # loop = asyncio.get_event_loop()

    redis_pool: Redis = await aioredis.create_redis_pool(
        ('redis', 6379), db=0,
    )
    app: Application = Application()

    app['redis'] = redis_pool
    app['http_client_session'] = ClientSession(
        raise_for_status=True, read_timeout=180, conn_timeout=180, trust_env=True,
    )
    app['tg_api']: TelegramAPI = TelegramAPI(app['http_client_session'])
    app['dispatcher'] = Dispatcher(app['redis'], app['tg_api'], app['http_client_session'])

    app.router.add_route('POST', '/webhook/', WebhookHandler)
    setup(app)
    app.on_startup.append(init_webhook)
    app.on_shutdown.append(close_client_session)
    app.on_cleanup.append(close_client_session)
    app.on_shutdown.append(close_redis)

    return app


async def run_server():
    app: Application = await http_app_factory()
    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, 'localhost', 8080)
    await site.start()
    await runner.cleanup()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_server())
    except KeyboardInterrupt:
        pass
    loop.close()
