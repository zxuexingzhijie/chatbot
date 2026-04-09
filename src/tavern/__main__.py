from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def _run_game(config_path: str = "config.yaml") -> None:
    from tavern.cli.app import GameApp

    app = GameApp(config_path=config_path)
    asyncio.run(app.run())


def main() -> None:
    parser = argparse.ArgumentParser(prog="tavern", description="CLI 互动小说游戏")
    sub = parser.add_subparsers(dest="command")

    run_parser = sub.add_parser("run", help="启动游戏")
    run_parser.add_argument("--config", default="config.yaml", help="配置文件路径")

    create_parser = sub.add_parser("create-scenario", help="创建新场景模板")
    create_parser.add_argument("name", help="场景名称（用作目录名）")
    create_parser.add_argument(
        "--dir",
        default="data/scenarios",
        help="场景父目录（默认: data/scenarios）",
    )

    args = parser.parse_args()

    if args.command == "create-scenario":
        from tavern.world.scenario import scaffold_scenario

        target = scaffold_scenario(args.name, Path(args.dir))
        print(f"场景模板已创建: {target}")
    else:
        config_path = getattr(args, "config", "config.yaml")
        _run_game(config_path)


if __name__ == "__main__":
    main()
