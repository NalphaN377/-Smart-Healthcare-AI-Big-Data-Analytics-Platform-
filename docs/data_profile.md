# Data Profile

- Generated: 2026-08-18T11:06:09
- File path: `/Users/liyichen/Documents/沟槽实习/009 医养项目数据/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv/Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv`
- File size: 793.81 MiB
- Format: csv
- Encoding: utf-8-sig
- Delimiter: `,`
- Total rows: 2,101,588
- Source field count: 33
- Mapped medical field count: 33 / 33

## Source fields

`Hospital Service Area`, `Hospital County`, `Operating Certificate Number`, `Permanent Facility Id`, `Facility Name`, `Age Group`, `Zip Code - 3 digits`, `Gender`, `Race`, `Ethnicity`, `Length of Stay`, `Type of Admission`, `Patient Disposition`, `Discharge Year`, `CCSR Diagnosis Code`, `CCSR Diagnosis Description`, `CCSR Procedure Code`, `CCSR Procedure Description`, `APR DRG Code`, `APR DRG Description`, `APR MDC Code`, `APR MDC Description`, `APR Severity of Illness Code`, `APR Severity of Illness Description`, `APR Risk of Mortality`, `APR Medical Surgical Description`, `Payment Typology 1`, `Payment Typology 2`, `Payment Typology 3`, `Birth Weight`, `Emergency Department Indicator`, `Total Charges`, `Total Costs`

## Column mapping

- `Hospital Service Area` → `hospital_service_area`
- `Hospital County` → `hospital_county`
- `Operating Certificate Number` → `operating_certificate_number`
- `Permanent Facility Id` → `facility_id`
- `Facility Name` → `facility_name`
- `Age Group` → `age_group`
- `Zip Code - 3 digits` → `zip_code_3_digits`
- `Gender` → `gender`
- `Race` → `race`
- `Ethnicity` → `ethnicity`
- `Length of Stay` → `length_of_stay`
- `Type of Admission` → `admission_type`
- `Patient Disposition` → `patient_disposition`
- `Discharge Year` → `discharge_year`
- `CCSR Diagnosis Code` → `diagnosis_code`
- `CCSR Diagnosis Description` → `diagnosis_description`
- `CCSR Procedure Code` → `procedure_code`
- `CCSR Procedure Description` → `procedure_description`
- `APR DRG Code` → `apr_drg_code`
- `APR DRG Description` → `apr_drg_description`
- `APR MDC Code` → `apr_mdc_code`
- `APR MDC Description` → `apr_mdc_description`
- `APR Severity of Illness Code` → `severity_code`
- `APR Severity of Illness Description` → `severity`
- `APR Risk of Mortality` → `mortality_risk`
- `APR Medical Surgical Description` → `medical_surgical_description`
- `Payment Typology 1` → `payment_type_1`
- `Payment Typology 2` → `payment_type_2`
- `Payment Typology 3` → `payment_type_3`
- `Birth Weight` → `birth_weight`
- `Emergency Department Indicator` → `emergency_indicator`
- `Total Charges` → `total_charges`
- `Total Costs` → `total_costs`

## Required fields missing

- None

## Metric definitions

- Medical institution count: **205**
- Definition: case-sensitive distinct cleaned, non-null and non-empty `facility_name`; `facility_id` is not used for this metric.

## Column statistics

| Internal field | Observed type | Missing | Missing rate | Unique values | Numeric statistics |
|---|---:|---:|---:|---:|---|
| hospital_service_area | string | 10,642 | 0.51% | 8 | - |
| hospital_county | string | 10,642 | 0.51% | 57 | - |
| operating_certificate_number | string | 12,091 | 0.58% | 168 | - |
| facility_id | Int64 | 10,642 | 0.51% | 205 | count=2,090,946, min=1.00, mean=1,033.84, max=10,355.00, std=709.41 |
| facility_name | string | 0 | 0.00% | 205 | - |
| age_group | string | 0 | 0.00% | 5 | - |
| zip_code_3_digits | string | 45,062 | 2.14% | 50 | - |
| gender | string | 0 | 0.00% | 3 | - |
| race | string | 0 | 0.00% | 4 | - |
| ethnicity | string | 198,543 | 9.45% | 3 | - |
| length_of_stay_raw | string | 0 | 0.00% | 120 | - |
| length_of_stay | Int64 | 0 | 0.00% | 120 | count=2,101,588, min=1.00, mean=5.74, max=120.00, std=8.42 |
| admission_type | string | 1,164 | 0.06% | 5 | - |
| patient_disposition | string | 0 | 0.00% | 19 | - |
| discharge_year | Int64 | 0 | 0.00% | 1 | count=2,101,588, min=2,021.00, mean=2,021.00, max=2,021.00, std=0.00 |
| diagnosis_code | string | 1,634 | 0.08% | 477 | - |
| diagnosis_description | string | 1,634 | 0.08% | 477 | - |
| procedure_code | string | 576,021 | 27.41% | 320 | - |
| procedure_description | string | 576,021 | 27.41% | 320 | - |
| apr_drg_code | Int64 | 0 | 0.00% | 334 | count=2,101,588, min=1.00, mean=414.11, max=956.00, std=244.23 |
| apr_drg_description | string | 0 | 0.00% | 334 | - |
| apr_mdc_code | Int64 | 0 | 0.00% | 26 | count=2,101,588, min=0.00, mean=10.29, max=25.00, std=5.96 |
| apr_mdc_description | string | 0 | 0.00% | 26 | - |
| severity_code | Int64 | 0 | 0.00% | 5 | count=2,101,588, min=0.00, mean=2.12, max=4.00, std=0.96 |
| severity | string | 2,550 | 0.12% | 4 | - |
| mortality_risk | string | 2,550 | 0.12% | 4 | - |
| medical_surgical_description | string | 0 | 0.00% | 3 | - |
| payment_type_1 | string | 0 | 0.00% | 9 | - |
| payment_type_2 | string | 1,072,245 | 51.02% | 9 | - |
| payment_type_3 | string | 1,768,881 | 84.17% | 9 | - |
| birth_weight | Int64 | 1,898,104 | 90.32% | 68 | count=203,484, min=400.00, mean=3,192.40, max=8,700.00, std=580.11 |
| emergency_indicator | boolean | 0 | 0.00% | 2 | - |
| total_charges | Float64 | 0 | 0.00% | 49,986+（下限） | count=2,101,588, min=0.34, mean=73,305.42, max=17,935,752.00, std=149,201.91 |
| total_costs | Float64 | 0 | 0.00% | 49,971+（下限） | count=2,101,588, min=0.15, mean=21,990.13, max=12,311,280.35, std=47,099.81 |

Unique counts marked “下限” reached the 50,000-value memory cap. Numeric statistics are calculated from normalized values.

## Categorical Top values

### age_group

`70 or Older` (619,644), `50 to 69` (584,480), `30 to 49` (415,681), `0 to 17` (289,732), `18 to 29` (192,051)
### birth_weight

`3200` (16,852), `3300` (16,691), `3400` (16,000), `3100` (15,938), `3000` (14,409), `3500` (14,394), `3600` (12,620), `2900` (11,985), `3700` (10,448), `2800` (9,930)
### diagnosis_description

`LIVEBORN` (199,014), `SEPTICEMIA` (138,035), `CORONAVIRUS DISEASE 2019 (COVID-19)` (82,597), `HEART FAILURE` (58,562), `COMPLICATIONS SPECIFIED DURING CHILDBIRTH` (40,711), `DIABETES MELLITUS WITH COMPLICATION` (40,529), `ALCOHOL-RELATED DISORDERS` (39,326), `SCHIZOPHRENIA SPECTRUM AND OTHER PSYCHOTIC DISORDERS` (37,204), `OSTEOARTHRITIS` (35,562), `CARDIAC DYSRHYTHMIAS` (33,849)
### discharge_year

`2021` (2,101,588)
### emergency_indicator

`True` (1,316,237), `False` (785,351)
### gender

`F` (1,145,483), `M` (955,949), `U` (156)
### length_of_stay

`2` (464,163), `1` (369,933), `3` (309,565), `4` (202,761), `5` (142,868), `6` (106,190), `7` (84,319), `8` (64,312), `9` (49,396), `10` (40,017)
### payment_type_1

`Medicare` (826,250), `Medicaid` (646,300), `Private Health Insurance` (307,242), `Blue Cross/Blue Shield` (224,090), `Managed Care, Unspecified` (28,229), `Self-Pay` (27,107), `Miscellaneous/Other` (22,526), `Federal/State/Local/VA` (18,604), `Department of Corrections` (1,240)
### severity

`Moderate` (760,535), `Minor` (638,227), `Major` (499,474), `Extreme` (200,802)
### total_charges

`9730.0` (514), `9760.23` (499), `3442.0` (398), `8600.04` (369), `17860.23` (290), `14845.33` (269), `14773.38` (255), `25478.19` (244), `7994.08` (216), `4061.08` (215)
### total_costs

`548.32` (520), `563.67` (499), `2228.82` (438), `1553.22` (399), `845.4` (289), `9027.04` (245), `2467.89` (216), `1250.44` (215), `836.84` (208), `2323.06` (206)

## Duplicate estimate

- Rows examined for duplicate estimation: 1,000,000
- Duplicate rows observed: 2,283
- Estimated duplicate rate in the tracked prefix: 0.2283%
- Method: stable full-business-row hash, capped at 1,000,000 rows to bound memory.

## Anomalies

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
