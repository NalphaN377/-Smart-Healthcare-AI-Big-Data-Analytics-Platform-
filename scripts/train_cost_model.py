"""训练并激活住院总成本估算模型。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ml.cost_model import train_cost_model, train_future_cost_model  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="训练住院费用预测模型")
    parser.add_argument("--sample-per-year", type=int, default=50_000)
    parser.add_argument(
        "--mode", choices=("encoded", "future", "all"), default="all",
        help="encoded=已编码病例最终成本；future=待入院未来病例成本；all=训练两者",
    )
    args = parser.parse_args()
    results = {}
    if args.mode in {"encoded", "all"}:
        results["encoded"] = train_cost_model(args.sample_per_year)
    if args.mode in {"future", "all"}:
        results["future"] = train_future_cost_model(args.sample_per_year)
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
