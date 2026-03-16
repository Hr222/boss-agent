"""Controller layer exports for the MVC surface."""

from src.controllers.console_command import main as console_main
from src.controllers.console_controller import ConsoleController

__all__ = ["ConsoleController", "console_main"]
