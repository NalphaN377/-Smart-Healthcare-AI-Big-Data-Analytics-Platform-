"""重建运营总览预汇总表。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.service_layer.analysis.dashboard_stats import refresh_dashboard_stats  # noqa: E402

if __name__ == "__main__":
    print(json.dumps(refresh_dashboard_stats(), ensure_ascii=False, indent=2, default=str))
