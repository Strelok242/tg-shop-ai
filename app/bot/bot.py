import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.init_db import init_db
from app.db.user_repo import upsert_user

from aiogram.filters import Command, CommandStart
from app.db.product_repo import list_active_products

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

@dp.message(Command("catalog"))
async def cmd_catalog(message: Message) -> None:
    products = list_active_products(limit=20)
    if not products:
        await message.answer("Каталог пуст. Админ ещё не добавил товары.")
        return

    lines = ["Каталог товаров:"]
    for p in products:
        price = p.price_cents / 100
        lines.append(f"- {p.name} ({p.sku}) — {price:.2f} ₽")

    await message.answer("\n".join(lines))


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
