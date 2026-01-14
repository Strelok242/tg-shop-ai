import os
from decimal import Decimal, InvalidOperation

from flask import Flask, flash, redirect, render_template, request, url_for

from app.db.database import SessionLocal
from app.db.init_db import init_db
from app.db.models import Product


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

    # гарантируем, что таблицы есть
    init_db()

    @app.get("/")
    def index() -> str:
        return "tg-shop-ai web is running"

    @app.route("/admin/products", methods=["GET", "POST"])
    def admin_products():
        # На будущее: тут будет авторизация администратора (TODO)
        session = SessionLocal()
        try:
            if request.method == "POST":
                sku = (request.form.get("sku") or "").strip()
                name = (request.form.get("name") or "").strip()
                description = (request.form.get("description") or "").strip() or None
                price_str = (request.form.get("price_rub") or "").strip()
                is_active = request.form.get("is_active") == "on"

                if not sku or not name or not price_str:
                    flash("Заполни SKU, название и цену.", "error")
                    return redirect(url_for("admin_products"))

                exists = session.query(Product).filter(Product.sku == sku).one_or_none()
                if exists is not None:
                    flash("Такой SKU уже существует.", "error")
                    return redirect(url_for("admin_products"))

                try:
                    price = Decimal(price_str.replace(",", "."))
                    price_cents = int((price * 100).to_integral_value())
                except (InvalidOperation, ValueError):
                    flash("Цена некорректная. Пример: 499.00", "error")
                    return redirect(url_for("admin_products"))

                if price_cents < 0:
                    flash("Цена не может быть отрицательной.", "error")
                    return redirect(url_for("admin_products"))

                product = Product(
                    sku=sku,
                    name=name,
                    description=description,
                    price_cents=price_cents,
                    is_active=is_active,
                )
                session.add(product)
                session.commit()

                flash("Товар добавлен ✅", "ok")
                return redirect(url_for("admin_products"))

            products = session.query(Product).order_by(Product.id).all()
            return render_template("admin_products.html", products=products)
        finally:
            session.close()

    return app
