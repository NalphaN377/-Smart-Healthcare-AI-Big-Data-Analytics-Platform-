import pandas as pd

from app.data_layer.quality import QualityAccumulator, assess


def sample_frame():
    return pd.DataFrame({
        "Facility Name": ["A", "B"],
        "Age Group": ["30 to 49", "50 to 69"],
        "Length of Stay": ["3", "-1"],
        "Discharge Year": ["2021", "1999"],
        "CCSR Diagnosis Description": ["Disease A", "Disease B"],
        "Payment Typology 1": ["Medicare", "Medicaid"],
        "Total Charges": ["1,200", "bad"],
        "Total Costs": ["800", "-2"],
        "Gender": ["F", "X"],
        "Emergency Department Indicator": ["Y", "?"],
        "APR Risk of Mortality": ["Minor", "Unknown"],
    })


def test_quality_report_has_all_dimensions():
    report = assess(sample_frame())
    assert set(report) == {"completeness", "accuracy", "consistency", "timeliness", "uniqueness", "sample_size", "overall"}
    assert report["sample_size"] == 2
    assert 0 <= report["overall"] <= 1
    assert report["timeliness"] == 0.5


def test_accumulator_weights_chunks():
    accumulator = QualityAccumulator()
    frame = sample_frame()
    accumulator.update(frame.iloc[:1])
    accumulator.update(frame.iloc[1:])
    report = accumulator.result()
    assert report["sample_size"] == 2
    assert report["uniqueness"] == 1.0
    assert report["timeliness"] == 0.5

