# Data Quality Report

- Generated: 2026-08-18T10:37:21
- Source (repository-relative): `009 医养项目数据/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv`
- Clean output (repository-relative): `data/processed/hospital_discharges_clean.parquet`
- Elapsed time: 59.27 seconds

## Row reconciliation

- Original rows: 2,101,588
- Exact duplicate rows removed: 7,105
- Clean rows: 2,094,483
- Reconciled: **True**

## Quality dimensions

| Dimension | Score | Method |
|---|---:|---|
| Completeness | 92.04% | Non-null cells / all canonical output cells |
| Consistency | 100.00% | Valid year, emergency flag and length-of-stay rules |
| Validity | 99.97% | Six core medical/numeric rule checks |
| Duplicate rate | 0.3381% | Exact normalized business-row hash |

## Source fields missing

- None

## Rule actions and anomalies

- `birth_weight_cleared`: 3,254
- `invalid_apr_drg_code`: 0
- `invalid_apr_mdc_code`: 0
- `invalid_discharge_year`: 0
- `invalid_emergency_indicator`: 0
- `invalid_facility_id`: 0
- `invalid_length_of_stay`: 0
- `invalid_severity_code`: 0
- `invalid_total_charges`: 0
- `invalid_total_costs`: 0
- `negative_total_charges`: 0
- `negative_total_costs`: 0

Birth weight is retained only for records whose admission/DRG/MDC context identifies a newborn or neonate; zero and values above 15,000 g are null. `120+` length of stay becomes numeric `120` while the original text is retained.
