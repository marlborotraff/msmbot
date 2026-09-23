from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from db.database import init_db
from handlers import admin, auth, generate, menu
from middlewares.access import AccessMiddleware
from renderer.output_cleanup import cleanup_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bot")


async def main() -> None:
    config.validate()

    await init_db()
    await generate.start_html_renderer()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    access_mw = AccessMiddleware()
    dp.message.middleware(access_mw)
    dp.callback_query.middleware(access_mw)

    dp.include_router(auth.router)
    dp.include_router(admin.router)
    dp.include_router(menu.router)
    dp.include_router(generate.router)

    cleanup_task = asyncio.create_task(cleanup_loop(config.OUTPUT_DIR))
    logger.info("Бот запущен")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task
        await generate.stop_html_renderer()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
