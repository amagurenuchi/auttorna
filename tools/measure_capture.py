"""Entry point reserved for M3 capture/inference measurements."""

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure capture and inference latency")
    parser.add_argument("--config", default="config/default.yaml")
    parser.parse_args()
    parser.error("capture measurement is planned for M3")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
