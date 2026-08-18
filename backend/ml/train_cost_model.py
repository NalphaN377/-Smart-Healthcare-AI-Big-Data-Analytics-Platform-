#!/usr/bin/env python3
"""Train a bounded-memory inpatient cost estimator from the official Parquet."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FEATURES = [
    "age_group",
    "gender",
    "admission_type",
    "diagnosis_code",
    "severity",
    "mortality_risk",
    "medical_surgical_description",
    "emergency_indicator",
    "payment_type_1",
]
TARGET = "total_costs"
LEAKAGE_EXCLUSIONS = [
    "total_costs",
    "total_charges",
    "source_file",
    "source_row_number",
    "record_hash",
    "created_at",
    "length_of_stay",
]


def sample_parquet(
    input_path: Path,
    sample_size: int,
    batch_size: int,
    random_state: int,
) -> tuple[pd.DataFrame, dict[str, list[str]], int]:
    parquet = pq.ParquetFile(input_path)
    total_rows = int(parquet.metadata.num_rows)
    fraction = min(1.0, sample_size * 1.25 / total_rows)
    parts = []
    feature_options = {feature: set() for feature in FEATURES}
    for batch_index, batch in enumerate(
        parquet.iter_batches(batch_size=batch_size, columns=[*FEATURES, TARGET]),
        start=1,
    ):
        frame = batch.to_pandas()
        valid_target = frame[TARGET].notna() & np.isfinite(frame[TARGET]) & frame[TARGET].ge(0)
        frame = frame.loc[valid_target]
        for feature in FEATURES:
            feature_options[feature].update(str(value) for value in frame[feature].dropna().unique())
        if fraction >= 1:
            parts.append(frame)
        else:
            parts.append(
                frame.sample(
                    frac=fraction,
                    random_state=random_state + batch_index,
                )
            )
    sampled = pd.concat(parts, ignore_index=True)
    if len(sampled) < sample_size:
        raise RuntimeError(
            f"only {len(sampled):,} valid rows sampled; requested {sample_size:,}"
        )
    sampled = sampled.sample(n=sample_size, random_state=random_state).reset_index(drop=True)
    options = {feature: sorted(values) for feature, values in feature_options.items()}
    return sampled, options, total_rows


def train(frame: pd.DataFrame, random_state: int, max_iter: int):
    from sklearn.compose import TransformedTargetRegressor
    from sklearn.dummy import DummyRegressor
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OrdinalEncoder

    x = frame[FEATURES].fillna("__MISSING__").astype(str)
    y = frame[TARGET].astype(float)
    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=0.2,
        random_state=random_state,
    )

    pipeline = Pipeline(
        [
            (
                "encoder",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    min_frequency=20,
                    max_categories=128,
                ),
            ),
            (
                "regressor",
                HistGradientBoostingRegressor(
                    categorical_features=list(range(len(FEATURES))),
                    learning_rate=0.08,
                    max_iter=max_iter,
                    max_leaf_nodes=31,
                    min_samples_leaf=30,
                    l2_regularization=1.0,
                    early_stopping=True,
                    random_state=random_state,
                ),
            ),
        ]
    )
    model = TransformedTargetRegressor(
        regressor=pipeline,
        func=np.log1p,
        inverse_func=np.expm1,
        check_inverse=False,
    )
    model.fit(x_train, y_train)
    predictions = np.maximum(0, model.predict(x_test))

    baseline = DummyRegressor(strategy="median")
    baseline.fit(np.zeros((len(y_train), 1)), y_train)
    baseline_predictions = baseline.predict(np.zeros((len(y_test), 1)))
    metrics = {
        "mae": round(float(mean_absolute_error(y_test, predictions)), 2),
        "rmse": round(float(np.sqrt(mean_squared_error(y_test, predictions))), 2),
        "r2": round(float(r2_score(y_test, predictions)), 4),
        "baseline_mae": round(float(mean_absolute_error(y_test, baseline_predictions)), 2),
    }
    return model, metrics, len(x_train), len(x_test)


def write_report(path: Path, metadata: dict) -> None:
    metrics = metadata["metrics"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""# Inpatient Cost Prediction Report

- Generated: {metadata['trained_at']}
- Dataset: `{metadata['dataset']}` ({metadata['dataset_rows']:,} cleaned records)
- Target: `{metadata['target']}`
- Training sample: {metadata['sample_size']:,} rows
- Train/test split: {metadata['train_rows']:,} / {metadata['test_rows']:,}
- Random state: {metadata['random_state']}
- Model: {metadata['model']}

## Features

{chr(10).join(f'- `{feature}`' for feature in metadata['features'])}

`total_costs`, `total_charges`, import metadata, row hashes and length of stay are excluded. The model therefore does not use the target, a direct charge proxy, or post-stay duration as an input.

## Held-out metrics

| Metric | Value |
|---|---:|
| MAE | {metrics['mae']:,.2f} |
| RMSE | {metrics['rmse']:,.2f} |
| R² | {metrics['r2']:.4f} |
| Median baseline MAE | {metrics['baseline_mae']:,.2f} |

## Sampling and leakage controls

The official Parquet is streamed in batches. A deterministic, row-group-spanning sample is selected and then split with a fixed random state. Encoding and model fitting occur only after the train/test split inside the estimator pipeline. No target-derived feature is used.

## Interpretation and limitations

This is a record-level administrative cost estimator for data-analysis coursework. Diagnosis and severity availability depends on workflow and may be finalized during or after a stay, so the model must not be represented as a guaranteed pre-admission forecast. It is not a medical diagnosis, clinical decision, billing or reimbursement model. Extreme costs are heavy-tailed, and a point prediction is not a confidence interval.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default=str(PROJECT_ROOT / "data/processed/hospital_discharges_clean.parquet"),
    )
    parser.add_argument("--sample-size", type=int, default=200_000)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--max-iter", type=int, default=150)
    parser.add_argument(
        "--model-output",
        default=str(PROJECT_ROOT / "backend/ml/artifacts/cost_model.joblib"),
    )
    parser.add_argument(
        "--metadata-output",
        default=str(PROJECT_ROOT / "backend/ml/model_metadata.json"),
    )
    parser.add_argument(
        "--report-output",
        default=str(PROJECT_ROOT / "docs/ml_cost_prediction_report.md"),
    )
    args = parser.parse_args()
    if min(args.sample_size, args.batch_size, args.max_iter) < 1:
        parser.error("sample size, batch size and max iterations must be positive")
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"cleaned Parquet not found: {input_path}")

    started = perf_counter()
    frame, feature_options, dataset_rows = sample_parquet(
        input_path,
        args.sample_size,
        args.batch_size,
        args.random_state,
    )
    model, metrics, train_rows, test_rows = train(
        frame,
        args.random_state,
        args.max_iter,
    )
    import joblib
    import sklearn

    model_output = Path(args.model_output).resolve()
    model_output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_output, compress=3)
    trained_at = datetime.now(UTC).isoformat(timespec="seconds")
    metadata = {
        "model_version": f"cost-hgb-v1-{datetime.now(UTC).strftime('%Y%m%d')}",
        "trained_at": trained_at,
        "dataset": input_path.name,
        "dataset_rows": dataset_rows,
        "target": TARGET,
        "features": FEATURES,
        "leakage_exclusions": LEAKAGE_EXCLUSIONS,
        "sample_size": len(frame),
        "train_rows": train_rows,
        "test_rows": test_rows,
        "random_state": args.random_state,
        "model": "OrdinalEncoder + log-target HistGradientBoostingRegressor",
        "scikit_learn_version": sklearn.__version__,
        "metrics": metrics,
        "feature_options": feature_options,
        "training_seconds": round(perf_counter() - started, 2),
    }
    metadata_output = Path(args.metadata_output).resolve()
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_report(Path(args.report_output).resolve(), metadata)
    print(
        json.dumps(
            {
                "model_version": metadata["model_version"],
                "dataset_rows": dataset_rows,
                "sample_size": len(frame),
                "train_rows": train_rows,
                "test_rows": test_rows,
                "metrics": metrics,
                "training_seconds": metadata["training_seconds"],
                "artifact_bytes": model_output.stat().st_size,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
