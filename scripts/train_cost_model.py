"""训练并激活住院总成本估算模型。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ml.cost_model import train_cost_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="训练住院最终总成本估算模型")
    parser.add_argument("--sample-per-year", type=int, default=50_000)
    args = parser.parse_args()
    print(json.dumps(train_cost_model(args.sample_per_year), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
