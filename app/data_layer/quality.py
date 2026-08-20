"""数据质量评估（一期可见、二期可扩展为采样与问题明细服务）。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CRITICAL_FIELDS = [
    "Facility Name", "Age Group", "Length of Stay", "Discharge Year",
    "CCSR Diagnosis Description", "Payment Typology 1", "Total Charges", "Total Costs",
]
VALID_GENDERS = {"M", "F", "U"}
VALID_ED = {"Y", "N"}
VALID_RISK = {"Minor", "Moderate", "Major", "Extreme", ""}


def _ratio(valid: pd.Series) -> float:
    return float(valid.mean()) if len(valid) else 0.0


def completeness(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    fields = [field for field in CRITICAL_FIELDS if field in df.columns]
    if not fields:
        return 0.0
    present = df[fields].notna() & df[fields].astype(str).ne("")
    return float(present.to_numpy().mean())


def uniqueness(df: pd.DataFrame, subset=None) -> float:
    return float(len(df.drop_duplicates(subset=subset)) / len(df)) if len(df) else 0.0


def accuracy(df: pd.DataFrame) -> float:
    checks = []
    for column in ("Length of Stay", "Total Charges", "Total Costs"):
        if column in df.columns:
            values = pd.to_numeric(df[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
            checks.append(_ratio(values.notna() & values.ge(0) & ~np.isinf(values.fillna(0))))
    return float(np.mean(checks)) if checks else 0.0


def consistency(df: pd.DataFrame) -> float:
    checks = []
    if "Gender" in df.columns:
        checks.append(_ratio(df["Gender"].fillna("").isin(VALID_GENDERS)))
    if "Emergency Department Indicator" in df.columns:
        checks.append(_ratio(df["Emergency Department Indicator"].fillna("").isin(VALID_ED)))
    if "APR Risk of Mortality" in df.columns:
        checks.append(_ratio(df["APR Risk of Mortality"].fillna("").isin(VALID_RISK)))
    return float(np.mean(checks)) if checks else 0.0


def timeliness(df: pd.DataFrame) -> float:
    if "Discharge Year" not in df.columns or df.empty:
        return 0.0
    years = pd.to_numeric(df["Discharge Year"], errors="coerce")
    return _ratio(years.between(2000, pd.Timestamp.utcnow().year))


def assess(df: pd.DataFrame) -> dict:
    report = {
        "completeness": round(completeness(df), 4),
        "accuracy": round(accuracy(df), 4),
        "consistency": round(consistency(df), 4),
        "timeliness": round(timeliness(df), 4),
        "uniqueness": round(uniqueness(df), 4),
        "sample_size": int(len(df)),
    }
    report["overall"] = round(np.mean([report[k] for k in ("completeness", "accuracy", "consistency", "timeliness")]), 4)
    return report


@dataclass
class QualityAccumulator:
    """对分块数据做加权质量汇总，避免加载完整数据集。"""

    rows: int = 0
    weighted_completeness: float = 0
    weighted_accuracy: float = 0
    weighted_consistency: float = 0
    weighted_timeliness: float = 0
    duplicate_rows: int = 0

    def update(self, df: pd.DataFrame) -> None:
        count = len(df)
        if not count:
            return
        self.rows += count
        self.weighted_completeness += completeness(df) * count
        self.weighted_accuracy += accuracy(df) * count
        self.weighted_consistency += consistency(df) * count
        self.weighted_timeliness += timeliness(df) * count
        self.duplicate_rows += int(df.duplicated().sum())

    def result(self) -> dict:
        if not self.rows:
            return {key: 0.0 for key in ("completeness", "accuracy", "consistency", "timeliness", "uniqueness", "overall")} | {"sample_size": 0}
        report = {
            "completeness": round(self.weighted_completeness / self.rows, 4),
            "accuracy": round(self.weighted_accuracy / self.rows, 4),
            "consistency": round(self.weighted_consistency / self.rows, 4),
            "timeliness": round(self.weighted_timeliness / self.rows, 4),
            "uniqueness": round(1 - self.duplicate_rows / self.rows, 4),
            "sample_size": self.rows,
        }
        report["overall"] = round(np.mean([report[k] for k in ("completeness", "accuracy", "consistency", "timeliness")]), 4)
        return report
