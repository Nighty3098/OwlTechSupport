"""Entrypoint: python -m app"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from .config import load_config
from .db.engine import create_engine, create_sessionmaker, init_models
from .main import create_dispatcher


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    config = load_config()

    engine = create_engine(config.db)
    await init_models(engine)
    sessionmaker = create_sessionmaker(engine)

    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else None
    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = create_dispatcher(config, sessionmaker)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
