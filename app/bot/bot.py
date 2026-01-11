import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.init_db import init_db
from app.db.user_repo import upsert_user

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user = upsert_user(tg_id=tg_user.id, username=tg_user.username)
    await message.answer(
        f"Привет! Я tg-shop-ai bot.\n"
        f"Я записал тебя в БД: user_id={user.id}, tg_id={user.tg_id}, username={user.username}"
    )


@dp.message()
async def echo(message: Message) -> None:
    await message.answer(f"Эхо: {message.text}")


async def _main() -> None:
    # гарантируем наличие таблиц перед запуском
    init_db()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is not set. Create .env file in project root with:\n"
            "BOT_TOKEN=123456:ABCDEF..."
        )

    bot = Bot(token=token)
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(_main())
