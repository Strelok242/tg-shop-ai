from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Product


def seed_products() -> int:
    """
    Создаёт таблицы и добавляет тестовые товары, если их ещё нет.
    Возвращает количество добавленных товаров.
    """
    init_db()

    demo_products: list[dict] = [
        {"sku": "SKU-001", "name": "Кружка", "description": "Керамическая, 330 мл", "price_cents": 49900},
        {"sku": "SKU-002", "name": "Футболка", "description": "Хлопок, размер M", "price_cents": 129900},
        {"sku": "SKU-003", "name": "Блокнот", "description": "A5, 80 листов", "price_cents": 29900},
        {"sku": "SKU-004", "name": "Рюкзак", "description": "20 л, городcкой", "price_cents": 349900},
        {"sku": "SKU-005", "name": "Наушники", "description": "Проводные, 3.5 мм", "price_cents": 89900},
    ]

    session = SessionLocal()
    try:
        existing = session.query(Product).count()
        if existing > 0:
            return 0

        for p in demo_products:
            session.add(Product(**p))

        session.commit()
        return len(demo_products)
    finally:
        session.close()
