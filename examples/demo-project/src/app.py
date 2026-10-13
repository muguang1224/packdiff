"""Entry point for the demo service."""

from __future__ import annotations

import json

from src.util import load_config


def main() -> int:
    config = load_config("config.json")
    print(json.dumps(config, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
