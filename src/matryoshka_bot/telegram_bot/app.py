from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError

from matryoshka_bot.config.settings import BotSettings
from matryoshka_bot.telegram_bot.handlers import build_router


def run_telegram_bot(settings: BotSettings) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for --telegram mode")
    asyncio.run(_run(settings))


async def _run(settings: BotSettings) -> None:
    bot = Bot(token=settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(build_router(set(settings.telegram_allowed_chat_ids), settings))
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    except TelegramConflictError as exc:
        raise RuntimeError(
            "Telegram: уже запущен другой процесс с этим TELEGRAM_BOT_TOKEN (getUpdates конфликт). "
            "Остановите второй экземпляр бота или используйте другой токен."
        ) from exc
