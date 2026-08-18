# Inpatient Cost Prediction Report

- Generated: 2026-08-18T10:19:55+00:00
- Dataset: `hospital_discharges_clean.parquet` (2,094,483 cleaned records)
- Target: `total_costs`
- Training sample: 200,000 rows
- Train/test split: 160,000 / 40,000
- Random state: 42
- Model: OrdinalEncoder + log-target HistGradientBoostingRegressor

## Features

- `age_group`
- `gender`
- `admission_type`
- `diagnosis_code`
- `severity`
- `mortality_risk`
- `medical_surgical_description`
- `emergency_indicator`
- `payment_type_1`

`total_costs`, `total_charges`, import metadata, row hashes and length of stay are excluded. The model therefore does not use the target, a direct charge proxy, or post-stay duration as an input.

## Held-out metrics

| Metric | Value |
|---|---:|
| MAE | 12,461.03 |
| RMSE | 38,134.04 |
| R² | 0.2301 |
| Median baseline MAE | 15,863.92 |

## Sampling and leakage controls

The official Parquet is streamed in batches. A deterministic, row-group-spanning sample is selected and then split with a fixed random state. Encoding and model fitting occur only after the train/test split inside the estimator pipeline. No target-derived feature is used.

## Interpretation and limitations

This is a record-level administrative cost estimator for data-analysis coursework. Diagnosis and severity availability depends on workflow and may be finalized during or after a stay, so the model must not be represented as a guaranteed pre-admission forecast. It is not a medical diagnosis, clinical decision, billing or reimbursement model. Extreme costs are heavy-tailed, and a point prediction is not a confidence interval.
