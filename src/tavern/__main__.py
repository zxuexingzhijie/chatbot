import asyncio

from tavern.cli.app import GameApp


def main():
    app = GameApp()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
