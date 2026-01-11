import argparse
from dotenv import load_dotenv


def run_web() -> None:
    from app.web.app import create_app

    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)


def run_bot() -> None:
    from app.bot.bot import run

    run()


def init_db_cmd() -> None:
    from app.db.init_db import init_db

    init_db()
    print("DB initialized: tables created (if not existed).")


def main() -> None:
    load_dotenv()  # loads .env from project root

    parser = argparse.ArgumentParser(prog="tg-shop-ai")
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("web", help="Run Flask web server")
    subparsers.add_parser("bot", help="Run Telegram bot")
    subparsers.add_parser("init-db", help="Initialize database (create tables)")

    args = parser.parse_args()

    if args.command == "web":
        run_web()
    elif args.command == "bot":
        run_bot()
    elif args.command == "init-db":
        init_db_cmd()
    else:
        print("tg-shop-ai: project scaffold is OK")
        print("Use: python main.py web  |  python main.py bot  |  python main.py init-db")


if __name__ == "__main__":
    main()
