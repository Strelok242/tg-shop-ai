import argparse


def run_web() -> None:
    from app.web.app import create_app

    app = create_app()
    app.run(host="127.0.0.1", port=5000, debug=True)


def run_bot() -> None:
    print("Bot mode: not implemented yet (next step)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="tg-shop-ai")
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("web", help="Run Flask web server")
    subparsers.add_parser("bot", help="Run Telegram bot")

    args = parser.parse_args()

    if args.command == "web":
        run_web()
    elif args.command == "bot":
        run_bot()
    else:
        print("tg-shop-ai: project scaffold is OK")
        print("Use: python main.py web  |  python main.py bot")


if __name__ == "__main__":
    main()
