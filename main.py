#!/usr/bin/python3
import asyncio
import logging

from dispatcher import dispatch
from botclass import bot

log = logging.getLogger(__name__)
logging.basicConfig(level='DEBUG')


async def poll_updates():
    offset = None
    while True:
        success, updates = await bot.get_updates(offset)
        if not success:
            log.error(f"Error occured:{updates.get('description')}")
            await asyncio.sleep(1)
            continue

        offset = await dispatch(updates)


def run():
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(poll_updates())
    except KeyboardInterrupt:
        log.info("Interrupted with keyboard")
        pass
    finally:
        loop.run_until_complete(bot.clean())
        loop.close()


if __name__ == '__main__':
    run()
