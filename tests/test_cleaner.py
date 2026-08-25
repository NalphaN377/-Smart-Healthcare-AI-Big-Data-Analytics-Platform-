"""数据处理层清洗逻辑单元测试。

运行：pytest tests/test_cleaner.py
"""
import pandas as pd

from app.data_layer import cleaner


def test_clean_money_removes_comma():
    df = pd.DataFrame({
        "Total Charges": ["320,922.43", "1,234.00", "$500"],
        "Total Costs": ["60,241.34", "100", "80"],
    })
    cleaned = cleaner.clean_money(df)
    assert cleaned["Total Charges"].iloc[0] == 320922.43
    assert cleaned["Total Charges"].iloc[1] == 1234.0
    assert cleaned["Total Charges"].iloc[2] == 500.0


def test_clean_birth_weight_non_newborn():
    df = pd.DataFrame({
        "Type of Admission": ["Newborn", "Emergency", "Newborn"],
        "Birth Weight": ["03100", "N/A", "02800"],
    })
    cleaned = cleaner.clean_birth_weight(df)
    # 非新生儿记录置 None
    assert cleaned["Birth Weight"].iloc[1] is None
    # 新生儿记录保留
    assert cleaned["Birth Weight"].iloc[0] == "03100"


def test_drop_duplicates():
    df = pd.DataFrame({"a": [1, 1, 2], "b": [1, 1, 2]})
    out = cleaner.drop_duplicates(df)
    assert len(out) == 2


def test_cross_year_labels_are_normalized():
    df = pd.DataFrame({
        "Age Group": ["0 to 17", "50-69", "70 or Older"],
        "Hospital Service Area": ["Capital/Adirond", "New York City", "Capital/Adirondacks"],
        "Facility Name": ["MOUNT ST MARY`S", "A", "B"],
    })
    out = cleaner.normalize_cross_year_labels(df)
    assert out["Age Group"].tolist() == ["0-17", "50-69", "70+"]
    assert out["Hospital Service Area"].tolist() == [
        "Capital/Adirondacks", "New York City", "Capital/Adirondacks",
    ]
    assert out["Facility Name"].iloc[0] == "MOUNT ST MARY'S"
