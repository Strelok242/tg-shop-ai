import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.db.init_db import init_db
from app.db.user_repo import upsert_user

from aiogram.filters import Command, CommandStart
from app.db.product_repo import list_active_products

from app.db.order_repo import create_order_for_user
from app.db.order_query import list_orders_by_tg_id

from app.ai.service import generate_reply
from app.db.ai_repo import add_ai_log
from aiogram.filters import Command, CommandStart

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

@dp.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /buy <SKU>\nНапример: /buy SKU-001")
        return

    sku = parts[1].strip()
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    try:
        order = create_order_for_user(tg_id=tg_user.id, sku=sku, qty=1)
        await message.answer(
            f"Заказ создан ✅\n"
            f"order_id={order.id}\n"
            f"Статус: {order.status}\n"
            f"Сумма: {order.total_cents / 100:.2f} ₽"
        )
    except ValueError as e:
        await message.answer(f"Ошибка: {e}")

@dp.message(Command("ai"))
async def cmd_ai(message: Message) -> None:
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    parts = (message.text or "").split(maxsplit=1)
    prompt = parts[1] if len(parts) > 1 else ""

    reply = generate_reply(prompt)

    try:
        # логируем только если пользователь уже есть в БД
        add_ai_log(tg_id=tg_user.id, prompt=prompt, response=reply)
    except ValueError:
        # пользователь не делал /start — мягко просим сделать
        await message.answer("Сначала выполни /start, чтобы я мог вести историю запросов.")
        return

    await message.answer(reply)


@dp.message(Command("myorders"))
async def cmd_myorders(message: Message) -> None:
    tg_user = message.from_user
    if tg_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    orders = list_orders_by_tg_id(tg_id=tg_user.id, limit=5)
    if not orders:
        await message.answer("У тебя пока нет заказов. Используй /catalog и /buy <SKU>.")
        return

    lines = ["Твои последние заказы:"]
    for o in orders:
        lines.append(f"- order_id={o.id} | {o.status} | {o.total_cents / 100:.2f} ₽")

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
