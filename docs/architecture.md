# MVP Architecture and Design Notes

## Data flow

`raw dataset → chunked Pandas normalization → one Parquet → MySQL → SQL/PySpark aggregation → Flask → Vue/ECharts`

The raw source is opened read-only. Cleaning writes a hidden temporary Parquet next to the final processed path and atomically replaces only the processed output. A temporary SQLite primary-key table tracks row hashes across chunks and is removed after the run.

The cross-component institution metric is defined as the case-sensitive distinct count of cleaned, non-null and non-empty `facility_name`. It deliberately does not coalesce `facility_id`, because redacted records can have a valid placeholder name but no numeric identifier. MySQL uses a binary expression so its collation semantics match Pandas and Spark.

## Boundaries

- `app/utils`: source discovery, column contract, normalization.
- `app/repositories`: parameterized SQL only; no HTTP concerns.
- `app/services`: business operation boundary.
- `app/api`: parameter validation and response metadata.
- `app/ai`: provider protocol reserved for Phase 2.
- `spark/jobs`: independent local-mode batch analytics.

## Database indexes

The primary access patterns group or filter by hospital, age, year, diagnosis, severity and primary payment type. Those dimensions receive single-column BTREE indexes. `record_hash` is unique for idempotent import. Free-text descriptions, charges, costs and source metadata are not indexed because their selectivity/query value does not justify the write amplification and storage cost.

## Graceful degradation

Missing source fields remain nullable canonical columns and are listed as `Required field missing` in the profile. Analyses over a wholly missing dimension return an empty API collection. A single discharge year returns an explicit no-trend note. The AI endpoint returns HTTP 501 until a provider is configured.

## Verified compatibility

- Schema and queries: MySQL 9.3 local validation; DDL targets official MySQL 8.4.
- Spark: 4.1.1, Java 17, macOS arm64, `local[*]`.
- Frontend: Vue 3.5.40, ECharts 6.1.0, Vite 8.2.0.
