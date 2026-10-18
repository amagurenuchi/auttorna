import ctypes
import os

from screen_detector.debug import configure_logging


def ensure_debug_console() -> None:
    if os.name == "nt" and ctypes.windll.kernel32.GetConsoleWindow() == 0:
        ctypes.windll.kernel32.AllocConsole()


ensure_debug_console()
configure_logging()

from screen_detector.app import App

if __name__ == "__main__":
    App().run()
