# tg-shop-ai

Прототип интернет-магазина с Telegram-ботом и веб-интерфейсом (Flask) + модуль AI-помощника (заглушка) с логированием запросов в БД.

## Возможности (MVP)
- Telegram-бот:
  - `/start` — регистрация пользователя в БД
  - `/catalog` — показать каталог товаров из БД
  - `/buy <SKU>` — создать заказ и позицию заказа в БД
  - `/myorders` — вывести последние заказы пользователя
  - `/ai <текст>` — AI-заглушка: рекомендации/подсказки + логирование в БД (`ai_logs`)
- Web (Flask):
  - `/` — проверка работоспособности
  - `/admin/products` — простая “админка” товаров (добавление + список)
  - `/catalog` — публичный каталог
  - `/orders?tg_id=<id>` — страница заказов пользователя (прототип “личного кабинета”)
- База данных: SQLite + SQLAlchemy (таблицы: `users`, `products`, `orders`, `order_items`, `ai_logs`)

## Технологии
- Python 3.11
- aiogram (Telegram Bot API)
- Flask
- SQLAlchemy
- SQLite
- python-dotenv

## Структура проекта
- `app/bot/` — Telegram-бот
- `app/web/` — веб-приложение (Flask)
- `app/db/` — модели и работа с БД
- `app/ai/` — AI-модуль (заглушка) + логирование
- `data/` — локальные данные (файл БД **не коммитится**)

## Быстрый старт (Windows / PowerShell)

### 1) Клонирование и окружение
```powershell
git clone https://github.com/Strelok242/tg-shop-ai.git
cd tg-shop-ai

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Live demo (Render): https://tg-shop-ai.onrender.com/catalog
