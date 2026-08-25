"""大数据异常处理与数据类型标准化。

对应文档功能：
- 「大数据异常处理」：缺失值/异常值处理、去重；
  例：非新生儿的 Birth Weight 字段设为 N/A、去除重复住院记录。
- 「数据类型标准化」：例：移除 Total Charges 中的逗号并转浮点数、
  标准化日期、编码格式。
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# 逗号分隔的金额字段（需去除逗号 / 货币符号后转 float）
MONEY_FIELDS = ["Total Charges", "Total Costs"]

# 数值型字段（标准化为数值类型）
NUMERIC_FIELDS = [
    "Length of Stay", "Discharge Year", "APR Severity of Illness Code", *MONEY_FIELDS
]

REQUIRED_FIELDS = {
    "Facility Name", "Age Group", "Length of Stay", "Discharge Year",
    "CCSR Diagnosis Description", "Payment Typology 1", "Total Charges", "Total Costs",
}


def drop_duplicates(df: pd.DataFrame, subset=None, keep: str = "first") -> pd.DataFrame:
    """去除重复住院记录。

    Args:
        subset: 去重依据的列；默认 None 表示整行完全一致才算重复。
        keep: 'first' 保留首条 / 'last' 保留末条 / False 全部删除。
    """
    before = len(df)
    df = df.drop_duplicates(subset=subset, keep=keep)
    dropped = before - len(df)
    if dropped:
        logger.info("去重: %d -> %d 条（删除 %d 条）", before, len(df), dropped)
    return df


def clean_money(df: pd.DataFrame, columns=MONEY_FIELDS) -> pd.DataFrame:
    """金额字段去逗号 / 货币符号并转为 float。

    例：'320,922.43' -> 320922.43
    """
    for col in columns:
        if col not in df.columns:
            continue
        df[col] = (
            df[col].astype(str)
            .str.replace(",", "", regex=False)
            .str.replace("$", "", regex=False)
            .str.strip()
            .replace(["", "nan", "None", "N/A", "null"], np.nan)
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def clean_birth_weight(df: pd.DataFrame) -> pd.DataFrame:
    """非新生儿记录的 Birth Weight 置 N/A。

    业务规则：仅入院类型为 Newborn 的记录才保留出生体重，
    其余记录统一置空（None）。
    """
    col = "Birth Weight"
    if col in df.columns and "Type of Admission" in df.columns:
        mask = df["Type of Admission"] != "Newborn"
        df.loc[mask, col] = None
        logger.info("非新生儿 Birth Weight 置 N/A 记录数: %d", mask.sum())
    return df


def normalize_types(df: pd.DataFrame) -> pd.DataFrame:
    """数据类型标准化：数值字段转数值、编码格式统一。"""
    if "Length of Stay" in df.columns:
        # SPARCS 数据可能用 "120 +" 表示 120 天及以上。
        los = df["Length of Stay"].astype(str).str.extract(r"(\d+)", expand=False)
        df["Length of Stay"] = pd.to_numeric(los, errors="coerce").clip(lower=0).astype("Int64")
    for col in ("Discharge Year", "APR Severity of Illness Code"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in MONEY_FIELDS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)
    return df


def normalize_cross_year_labels(df: pd.DataFrame) -> pd.DataFrame:
    """归一化2021—2024年度间已确认的分类标签漂移。"""
    if "Age Group" in df.columns:
        df["Age Group"] = df["Age Group"].replace({
            "0 to 17": "0-17", "18 to 29": "18-29", "30 to 49": "30-49",
            "50 to 69": "50-69", "70 or Older": "70+", "70 and Older": "70+",
        })
    if "Hospital Service Area" in df.columns:
        df["Hospital Service Area"] = df["Hospital Service Area"].replace({
            "Capital/Adirond": "Capital/Adirondacks",
        })
    if "Facility Name" in df.columns:
        df["Facility Name"] = df["Facility Name"].str.replace("`", "'", regex=False)
    return df


def handle_missing(df: pd.DataFrame, fill_map: dict = None) -> pd.DataFrame:
    """缺失值处理：字符字段缺失填充空串，数值字段保持 NaN（后续由业务决定）。

    Args:
        fill_map: 可选，指定字段的填充值覆盖，如 {"Gender": "Unknown"}。
    """
    for col in df.columns:
        if col in (fill_map or {}):
            df[col] = df[col].fillna(fill_map[col])
        elif not pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].where(df[col].notna(), "")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """完整清洗流水线：去重 -> 金额清洗 -> 类型标准化 -> 缺失处理 -> 出生体重。

    注意：clean_birth_weight 必须放在 handle_missing 之后执行，
    否则非新生儿的 Birth Weight=None 会被 handle_missing 填成空串而丢失 N/A 语义。
    逐块调用时，对每个 chunk 单独执行本函数即可。
    """
    df = df.copy()  # 防御性拷贝，避免对上游视图原地修改触发 SettingWithCopyWarning
    df = drop_duplicates(df)
    df = clean_money(df)
    df = normalize_types(df)
    df = normalize_cross_year_labels(df)
    df = handle_missing(df)
    df = clean_birth_weight(df)
    return df


def validate_columns(df: pd.DataFrame, expected_columns) -> None:
    """校验源文件契约，防止字段漂移后静默错位入库。"""
    expected = list(expected_columns)
    missing = [column for column in expected if column not in df.columns]
    unknown = [column for column in df.columns if column not in expected]
    if missing or unknown:
        raise ValueError(f"数据字段不匹配，缺少={missing}，多出={unknown}")


def clean_with_stats(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """清洗并返回可审计统计信息。"""
    before = len(df)
    duplicate_count = int(df.duplicated().sum())
    cleaned = clean(df)
    invalid_required = int(cleaned[list(REQUIRED_FIELDS & set(cleaned.columns))].isna().all(axis=1).sum())
    if invalid_required:
        cleaned = cleaned.loc[~cleaned[list(REQUIRED_FIELDS & set(cleaned.columns))].isna().all(axis=1)]
    stats = {
        "rows_read": before,
        "rows_after_clean": len(cleaned),
        "duplicates_removed": duplicate_count,
        "invalid_rows_removed": invalid_required,
    }
    return cleaned, stats
