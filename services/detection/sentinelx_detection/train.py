"""Trains the Isolation Forest on the seeded synthetic baseline (D-049).

Usage: python -m sentinelx_detection.train [--output PATH]
Deterministic: the same code and dependency versions produce the same model version.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .anomaly import save, train
from .baseline import BaselineConfig
from .config import DEFAULT_MODEL_PATH


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentinelx_detection.train")
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args(argv)
    config = BaselineConfig()
    model = train(config)
    save(model, args.output, config)
    print(json.dumps({"event": "detection.model_trained", "version": model.version, "path": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
