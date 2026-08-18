#!/usr/bin/env python3
"""Profile the ten production aggregate query shapes without exposing credentials."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Config
from backend.app.database import connect_from_config


QUERIES = {
    "overview": """
        SELECT COUNT(*) AS total_records,
               COUNT(DISTINCT BINARY NULLIF(TRIM(facility_name), '')) AS facility_count,
               AVG(length_of_stay), AVG(total_charges), AVG(total_costs),
               AVG(CASE WHEN emergency_indicator = TRUE THEN 1.0 ELSE 0.0 END)
        FROM hospital_discharges
    """,
    "diseases_top": """
        SELECT diagnosis_description, COUNT(*) AS record_count
        FROM hospital_discharges
        WHERE diagnosis_description IS NOT NULL AND diagnosis_description <> ''
        GROUP BY diagnosis_description
        ORDER BY record_count DESC, diagnosis_description ASC LIMIT 10
    """,
    "diseases_cost": """
        SELECT diagnosis_description, COUNT(*) AS record_count,
               AVG(total_charges) AS avg_total_charges, AVG(total_costs) AS avg_total_costs
        FROM hospital_discharges
        WHERE diagnosis_description IS NOT NULL AND diagnosis_description <> ''
        GROUP BY diagnosis_description
        ORDER BY avg_total_charges DESC, record_count DESC LIMIT 10
    """,
    "hospitals_top": """
        SELECT facility_name, COUNT(*) AS record_count, AVG(length_of_stay)
        FROM hospital_discharges
        WHERE facility_name IS NOT NULL AND facility_name <> ''
        GROUP BY facility_name
        ORDER BY record_count DESC, facility_name ASC LIMIT 10
    """,
    "hospitals_cost": """
        SELECT facility_name, COUNT(*) AS record_count, AVG(total_charges),
               AVG(total_costs), AVG(length_of_stay)
        FROM hospital_discharges
        WHERE facility_name IS NOT NULL AND facility_name <> ''
        GROUP BY facility_name
        ORDER BY AVG(total_charges) DESC, record_count DESC LIMIT 10
    """,
    "age_distribution": """
        SELECT age_group, COUNT(*) AS record_count, AVG(length_of_stay)
        FROM hospital_discharges
        WHERE age_group IS NOT NULL AND age_group <> ''
        GROUP BY age_group ORDER BY record_count DESC, age_group ASC LIMIT 10
    """,
    "age_cost": """
        SELECT age_group, COUNT(*) AS record_count, AVG(total_charges),
               AVG(total_costs), AVG(length_of_stay)
        FROM hospital_discharges
        WHERE age_group IS NOT NULL AND age_group <> ''
        GROUP BY age_group ORDER BY age_group ASC LIMIT 10
    """,
    "payment_distribution": """
        SELECT payment_type_1, COUNT(*) AS record_count,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2)
        FROM hospital_discharges
        WHERE payment_type_1 IS NOT NULL AND payment_type_1 <> ''
        GROUP BY payment_type_1 ORDER BY record_count DESC, payment_type_1 ASC LIMIT 10
    """,
    "severity_distribution": """
        SELECT severity, COUNT(*) AS record_count, AVG(total_charges), AVG(length_of_stay)
        FROM hospital_discharges
        WHERE severity IS NOT NULL AND severity <> ''
        GROUP BY severity ORDER BY record_count DESC, severity ASC LIMIT 10
    """,
    "yearly_trends": """
        SELECT discharge_year, COUNT(*) AS record_count, AVG(total_charges), AVG(total_costs)
        FROM hospital_discharges
        WHERE discharge_year IS NOT NULL
        GROUP BY discharge_year ORDER BY discharge_year ASC LIMIT 20
    """,
}


def safe_config() -> dict:
    return {
        key: getattr(Config, key)
        for key in (
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_CONNECT_TIMEOUT",
            "MYSQL_READ_TIMEOUT",
            "MYSQL_WRITE_TIMEOUT",
        )
    }


def summarize_plan(plan: str) -> dict:
    rows = [
        int(float(value))
        for value in re.findall(r"actual time=[^\n]*? rows=([0-9.]+(?:e[+-]?\d+)?)", plan)
    ]
    access = (
        "table_scan"
        if "Table scan on hospital_discharges" in plan
        else "index_scan"
        if re.search(r"(?:Index|index).*scan on hospital_discharges", plan)
        else "other"
    )
    return {
        "access": access,
        "max_actual_rows": max(rows, default=None),
        "temporary_table": "temporary table" in plan.lower(),
        "sort": "Sort:" in plan,
        "plan": " ".join(plan.split()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="profile")
    args = parser.parse_args()
    connection = connect_from_config(safe_config())
    output = {"label": args.label, "indexes": [], "queries": {}}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW INDEX FROM hospital_discharges")
            output["indexes"] = [
                {
                    "name": row["Key_name"],
                    "column": row["Column_name"],
                    "sequence": int(row["Seq_in_index"]),
                    "unique": not bool(row["Non_unique"]),
                }
                for row in cursor.fetchall()
            ]
            for name, sql in QUERIES.items():
                started = perf_counter()
                cursor.execute("EXPLAIN ANALYZE " + sql)
                row = cursor.fetchone()
                elapsed_ms = round((perf_counter() - started) * 1000, 2)
                plan = str(next(iter(row.values())))
                output["queries"][name] = {
                    "duration_ms": elapsed_ms,
                    **summarize_plan(plan),
                }
    finally:
        connection.close()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
