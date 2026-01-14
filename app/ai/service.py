from __future__ import annotations

from app.db.product_repo import list_active_products


def generate_reply(prompt: str) -> str:
    """
    Заглушка ИИ:
    - если пользователь просит "подобрать/посоветовать", выдаём 3 первых товара
    - если спрашивает про каталог, подсказываем /catalog
    - иначе — короткий ответ + подсказка команд
    """
    text = (prompt or "").strip().lower()
    if not text:
        return "Напиши запрос после команды. Пример: /ai посоветуй подарок"

    if any(word in text for word in ["посовет", "подоб", "рекоменд", "подар", "что купить"]):
        products = list_active_products(limit=3)
        if not products:
            return "Пока нет товаров. Админ должен добавить товары в /admin/products."
        lines = ["Вот что могу предложить:"]
        for p in products:
            lines.append(f"- {p.name} ({p.sku}) — {p.price_cents/100:.2f} ₽")
        lines.append("Чтобы купить: /buy <SKU>")
        return "\n".join(lines)

    if "каталог" in text or "товары" in text:
        return "Открой каталог командой /catalog. Для покупки: /buy <SKU>"

    return (
        "Я прототип AI-помощника магазина. "
        "Могу подсказать товары: напиши /ai посоветуй что купить.\n"
        "Команды: /catalog, /buy <SKU>, /myorders"
    )
