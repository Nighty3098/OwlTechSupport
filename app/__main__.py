"""Entrypoint: python -m app"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

from .config import load_config
from .db.engine import create_engine, create_sessionmaker, init_models
from .main import create_dispatcher

RECONNECT_DELAY_SEC = 10

logger = logging.getLogger("app")


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    config = load_config()
    logger.info("Support chat: %s", config.support_chat)
    logger.info("Proxy: %s", "disabled" if not config.proxy_url else config.proxy_url)

    engine = create_engine(config.db)
    await init_models(engine)
    sessionmaker = create_sessionmaker(engine)
    logger.info("Database is ready")

    session = AiohttpSession(proxy=config.proxy_url) if config.proxy_url else None
    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = create_dispatcher(config, sessionmaker)

    try:
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                logger.info("Connected to Telegram, starting polling")
                await dp.start_polling(bot)
                break  # polling stopped cleanly (shutdown signal)
            except TelegramNetworkError as exc:
                logger.warning(
                    "Telegram is unreachable (%s). Retrying in %ss...",
                    exc,
                    RECONNECT_DELAY_SEC,
                )
                await asyncio.sleep(RECONNECT_DELAY_SEC)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
