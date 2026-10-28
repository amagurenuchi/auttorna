"""Entry point reserved for M8 latency calibration."""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate display and input latency")
    parser.add_argument("--config", default="config/default.yaml")
    parser.parse_args()
    parser.error("latency calibration is planned for M8")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
