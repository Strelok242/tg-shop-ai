import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

dp = Dispatcher()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer("Привет! Я tg-shop-ai bot. Пока умею только отвечать и эхо.")


@dp.message()
async def echo(message: Message) -> None:
    await message.answer(f"Эхо: {message.text}")


async def _main() -> None:
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
