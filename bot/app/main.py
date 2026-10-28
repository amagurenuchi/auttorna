"""Command-line entry point for the rebuilt bot."""

import argparse

from bot.util.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline StepMania/Etterna hybrid bot")
    parser.add_argument("--config", default="config/default.yaml", help="YAML configuration path")
    parser.add_argument("--chart", help="Chart file to schedule")
    parser.add_argument("--rate", type=float, default=1.0, help="Chart rate modifier")
    parser.add_argument("--gui", action="store_true", help="launch the Tkinter control GUI")
    parser.add_argument("--verbose", action="store_true", help="log every parsed note and input event")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    configure_logging(10 if args.verbose else 20)
    if args.gui:
        from bot.app.gui import BotGui
        BotGui().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
