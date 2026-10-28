"""Convenience launcher: ``python run_gui.py``."""

import sys

from bot.app.main import main


def _run() -> int:
    sys.argv.append("--gui")
    return main()


if __name__ == "__main__":
    raise SystemExit(_run())
