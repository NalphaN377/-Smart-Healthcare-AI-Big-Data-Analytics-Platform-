# Phase 3A MySQL Performance Baseline

Generated on 2026-08-18 against the production `hospital_discharges` table with 2,094,483 rows. Measurements use MySQL 8.4 `EXPLAIN ANALYZE`; no schema changes were made before this run.

## Existing indexes

| Index | Column | Purpose |
|---|---|---|
| PRIMARY | id | Row identity |
| uq_hospital_discharges_record_hash | record_hash | Idempotent import |
| idx_hospital_discharges_facility_id | facility_id | Facility filtering |
| idx_hospital_discharges_facility_name | facility_name | Facility filtering/grouping |
| idx_hospital_discharges_age_group | age_group | Age filtering/grouping |
| idx_hospital_discharges_discharge_year | discharge_year | Year filtering/grouping |
| idx_hospital_discharges_diagnosis_code | diagnosis_code | Diagnosis-code filtering |
| idx_hospital_discharges_severity | severity | Severity filtering/grouping |
| idx_hospital_discharges_payment_type_1 | payment_type_1 | Payment filtering/grouping |

## Baseline results

| Query | Duration (ms) | Access/plan summary | Actual rows flowing from source |
|---|---:|---|---:|
| overview | 3,382.81 | Full table scan and aggregate | 2,094,483 |
| diseases_top | 2,665.14 | Full table scan, temporary aggregate, Top-N sort | 2,094,483 |
| diseases_cost | 2,586.08 | Full table scan, temporary aggregate, Top-N sort | 2,094,483 |
| hospitals_top | 6,411.46 | facility_name index range scan, group aggregate, sort | 2,094,483 |
| hospitals_cost | 5,156.70 | facility_name index range scan, group aggregate, sort | 2,094,483 |
| age_distribution | 6,993.04 | age_group index range scan, group aggregate, sort | 2,094,483 |
| age_cost | 8,687.96 | age_group index range scan and group aggregate | 2,094,483 |
| payment_distribution | 761.87 | Covering payment index, temporary/window aggregate | 2,094,483 |
| severity_distribution | 5,798.79 | severity index range scan, group aggregate, sort | 2,094,483 |
| yearly_trends | 3,097.94 | discharge_year index range scan and group aggregate | 2,094,483 |

## Findings

- These are global OLAP aggregates. Even where MySQL uses an existing dimension index, it still consumes all 2,094,483 rows because every row contributes to a group or average.
- `discharge_year` has only one real value (2021), so a year-leading composite index has effectively no selectivity for the current data.
- A wide covering index containing charges, costs and length of stay could reduce lookups for selected queries, but would duplicate large numeric payloads, increase import/write cost and consume material disk space.
- `payment_distribution` already benefits from a compact covering index and is substantially faster than the metric-heavy aggregates.
- The highest-value Phase 3A optimization is therefore a bounded Redis cache for repeated Dashboard/Agent aggregate results, not a collection of speculative indexes.

The reproducible profiler is `backend/scripts/profile_sql.py`. It records index names and plans only; it never prints database credentials.
