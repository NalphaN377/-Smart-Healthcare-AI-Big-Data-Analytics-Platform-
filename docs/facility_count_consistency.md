# Facility Count Consistency Audit

- Audited: 2026-08-18
- Unified definition: **case-sensitive distinct cleaned, non-null and non-empty `facility_name`**
- Original medical data was read-only throughout this audit.

## Three-source results

| Check | Raw CSV | Cleaned Parquet | MySQL |
|---|---:|---:|---:|
| Rows | 2,101,588 | 2,094,483 | 2,094,483 |
| Distinct non-empty facility name | 205 | 205 | 205 |
| NULL facility name | 0 | 0 | 0 |
| Empty facility name | 0 | 0 | 0 |
| Whitespace-only facility name | 0 | 0 | 0 |
| Distinct after trim | 205 | 205 | 205 |
| Case-folded distinct | 205 | 205 | 205 |
| BOM/control/special-space rows | 0 | 0 | 0 |
| Distinct facility ID | 205 | 205 | 205 |
| Old `COALESCE(facility_id, facility_name)` count | 206 | 206 | 206 |

No case-only duplicate groups or normalization-changing facility names were found.

## Root cause

`facility_id` is missing on 10,642 raw rows and 10,633 deduplicated rows. All of those records use the valid facility name `Redacted for Confidentiality`. The former Spark and MySQL overview expressions counted 205 numeric facility-ID strings plus this one fallback name, producing 206. This was a mixed-key count, not an additional medical institution.

Profiling already counted cleaned `facility_name` and returned 205. Spark and MySQL/API overview now use the same name-only definition; MySQL applies binary distinct semantics to match Pandas and Spark if future data contains case-only variants.
