"""控制台主命令入口。"""

from src.controllers.console_controller import ConsoleController


def main() -> None:
    """启动控制台主循环。"""
    ConsoleController().run()


if __name__ == "__main__":
    main()
