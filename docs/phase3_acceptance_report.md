# Phase 3 Acceptance Report

Generated from actual local execution on 2026-08-18. Full end-to-end validation platform: macOS 15.6.1 Apple Silicon, Python 3.11.3, MySQL 8.4, Redis 7.4, Hadoop 3.4.3, Hive 4.1.0, Spark 4.1.1 local mode, Vue 3 and Vite 8.2.0.

## Acceptance scope

- Phase 3A: optional Redis analytics cache, persistent AI sessions, failure fallback and SQL profiling.
- Phase 3B: Parquet-derived machine-readable quality metrics, Flask APIs and Vue/ECharts dashboard.
- Phase 3C: leakage-controlled inpatient cost estimator, strict inference API and Vue form.
- Phase 3D: route-level code splitting, cross-platform audit, complete regression and documentation.

No original CSV was modified, no duplicate full Parquet was created, and no Docker volume was deleted or recreated.

## Automated tests

| Check | Actual result |
|---|---|
| Python/Flask/AI/Redis/Data Quality/ML pytest | 78 passed in 0.38 s |
| Vue production build | Passed; 624 modules in 236 ms |
| Browser console across four routes | 0 warnings/errors |

The 78 tests include cache hit/miss/key stability/TTL/error fallback, Redis session create/history/append/max turns/fallback, unchanged API payload behavior, data-quality snapshot errors and fields, ML input schema/leakage exclusions/inference/unavailable behavior, plus all Phase 1/2A/2B regressions.

## Redis and analytics performance

The project Redis container is healthy. Host port 6379 was already occupied by an unrelated local service, so this acceptance run used `127.0.0.1:6380` without stopping it. The official `redis:7.4-alpine` image is 16,790,154 bytes; the persistent AOF volume used 48 KiB at final measurement.

Redis is optional. Disabled/unreachable tests confirmed that analytics query the original repository and AI sessions fall back to memory without HTTP 500. `GET /api/system/cache/status` reported enabled=true, connected=true, backend=redis and ttl=300 without connection secrets.

| Aggregate | MySQL/cold (ms) | Redis hit (ms) |
|---|---:|---:|
| overview | 2,186.75 | 0.43 |
| diseases top | 1,909.49 | 0.50 |
| diseases cost | 2,396.12 | 0.37 |
| hospitals top | 5,039.93 | 0.78 |
| hospitals cost | 4,947.21 | 0.51 |
| age distribution | 7,050.00 | 0.59 |
| age cost | 8,348.59 | 0.43 |
| payment distribution | 634.43 | 0.45 |
| severity distribution | 5,939.08 | 0.41 |
| yearly trend | 3,087.19 | 0.34 |

A live repeated HTTP check after cache population returned overview in 15.72 ms wall time (3.26 ms cache-layer telemetry) and hospital cost in 3.35 ms wall time (1.35 ms cache-layer telemetry). These figures distinguish end-to-end HTTP time from the Redis wrapper micro-benchmark.

## MySQL profiling and index decision

`EXPLAIN ANALYZE` was run for all ten repository queries. Global aggregates consume all 2,094,483 rows even when MySQL selects an existing dimension index. The compact `payment_type_1` covering index is useful; low-cardinality year/age/severity aggregates and cost-bearing averages do not justify speculative wide indexes. No schema/index migration was applied. Redis is used for repeated fixed-dashboard/Agent aggregates instead of increasing database write and disk cost. Full plans are in `sql_performance_before.md` and `sql_performance_after.md`.

## Data quality

The metrics generator streamed the official Parquet and completed in 11.6 seconds. The committed JSON snapshot is 4 KiB and avoids per-page full scans.

| Metric | Actual value |
|---|---:|
| Total rows | 2,094,483 |
| Total columns | 37 |
| Facilities | 205 |
| Duplicates removed during cleaning | 7,105 |
| Duplicates remaining | 0 |
| Completeness | 92.04% |
| Validity | 100.00% |
| Consistency | 100.00% |

`diagnosis_description` has 1,634 missing values (0.0780%) and `severity` has 2,548 (0.1217%). The other eight reported critical fields are complete. Negative charges/costs, invalid LOS, invalid birth weight, invalid year and invalid emergency indicator are all zero after cleaning. Both quality APIs returned HTTP 200, and `/data-quality` rendered both ECharts and the field table.

## Cost prediction

The official training run streamed the 2,094,483-row Parquet, selected a deterministic 200,000-row sample, and split it into 160,000 training and 40,000 held-out records with random_state=42. Training took 3.15 seconds; the ignored joblib artifact is 264,126 bytes.

| Metric | Held-out result |
|---|---:|
| MAE | 12,461.03 |
| RMSE | 38,134.04 |
| R² | 0.2301 |
| Median baseline MAE | 15,863.92 |

Neither `total_costs`, `total_charges` nor `length_of_stay` is a feature. Source metadata, row number, record hash and created timestamp are also excluded. The live status API reported available=true and sample_size=200,000; an actual strict request returned predicted_cost=39,803.64. The browser form returned the same rounded US$39,804 result and displayed the disclaimer and held-out metrics.

This model is a coursework administrative cost estimator, not a medical diagnosis, clinical decision or billing system. Its low-to-moderate R² and heavy-tail error are reported rather than hidden.

## Frontend performance and browser acceptance

Dynamic route imports were applied to Dashboard, AI Chat, Data Quality and Cost Prediction. Initial minified JavaScript fell from 675.70 kB (233.32 kB gzip) to 89.49 kB (34.87 kB gzip), an 86.76% reduction. The route chunks are 5.03–8.05 kB. Selective `echarts/core` registration remains a shared 559.87 kB lazy chunk.

Browser acceptance verified:

- `/`: 2,094,483 records, 205 facilities, 5.7 average LOS, US$73,459 average charges; six charts rendered and the single-year trend showed unavailable.
- `/data-quality`: quality scores, 37 columns, 205 facilities, two charts and eight field rows rendered.
- `/cost-prediction`: model metadata loaded and a real prediction completed with disclaimer.
- `/ai`: configured provider label `openai_compatible / deepseek-v4-flash` and six valid example questions rendered.
- Console: no warnings or errors after the final reloads.

A cold dashboard can issue multiple expensive MySQL aggregates concurrently. Three requests exceeded the prior 15-second client limit while still completing successfully server-side; the finite frontend timeout is now 45 seconds, and subsequent Redis-backed loads completed normally.

## AI regression

A deterministic validation provider exercised ten real MySQL questions and three multi-turn groups in 75.221 seconds. All selected the expected allow-listed Tool; the unsupported 2020–2024 trend returned only the real 2021 scope and no line chart.

One deliberately limited real DeepSeek V4 Flash call was then made through the production endpoint:

- Question: `住院人数最多的五种疾病是什么？`
- Tool: `get_top_diseases(limit=5)`
- Tool latency: 2 ms (Redis hit)
- Routing latency: 2,844 ms
- Summary latency: 1,807 ms
- Total latency: 8,718 ms
- Token usage: 3,366 input, 161 output, 3,527 total
- Source: 2,094,483 cleaned records, year 2021
- Chart: controlled `horizontal_bar`

No SQL or JavaScript was generated by the LLM, and no credential was returned.

## Cross-system consistency

| System | Rows | Facilities | Result |
|---|---:|---:|---|
| Local cleaned Parquet metadata | 2,094,483 | 205 | Passed |
| MySQL `/api/overview` | 2,094,483 | 205 | Passed |
| HDFS single Parquet | 2,094,483 (Hive count) | 205 | Passed |
| Hive external table | 2,094,483 | 205 | Passed |
| Spark HDFS eight-analysis job | 2,094,483 | 205 | Passed in 13.19 s |
| Spark SQL via Hive Metastore | 2,094,483 | 205 | Passed in 5.52 s |

HDFS reports one live DataNode, one 102.8 MiB Parquet file, replication=1, zero missing/corrupt/under-replicated blocks. The full `verify_bigdata.sh` completed successfully with all 279 Hive artifacts already retrieved from the persistent Ivy cache.

## HTTP acceptance

All existing analytics endpoints plus `/api/system/cache/status`, both data-quality endpoints, both ML endpoints and `/api/ai/status` returned HTTP 200. `/api/ai/status` reported configured=true and model=deepseek-v4-flash without returning the API key. The live `/api/overview` remained 2,094,483 rows and 205 facilities.

## Cross-platform audit

- No source/configuration path contains a developer-specific home directory after Phase 3.
- Python paths are dynamically derived with `pathlib`; `backend/run.py` now imports from the repository root consistently.
- Compose does not hardcode a CPU platform; official multi-architecture images are used.
- Bash big-data scripts derive `PROJECT_ROOT` and are documented for execution inside WSL2.
- Windows 10/11 + Docker Desktop + WSL2 is supported by design and is the recommended Windows path, but was not falsely reported as physically tested.

## Disk usage

| Item | Final measurement |
|---|---:|
| Repository working tree | 1.8 GiB |
| Official local cleaned Parquet | 103 MiB |
| ML artifact | 260 KiB on disk |
| Frontend dist | 696 KiB |
| Redis image | 16.0 MiB |
| Redis data volume content | 48 KiB |
| Docker images (all projects) | 12.52 GiB |
| Docker local volumes (all projects) | 4.206 GiB |
| Host free space | 39 GiB |

No pruning or destructive cleanup was run.

## Git and security

Phase 3 milestone commits:

- `b7ac298 perf: add redis cache and persistent ai sessions`
- `4f838ac feat: add data quality monitoring dashboard`
- `0e40f7b feat: add inpatient cost prediction model`
- Phase 3D acceptance changes are included by the commit that adds this report.

`.env`, API keys, database passwords, model artifact, raw 793.81 MiB CSV, Docker volumes, caches, logs and the user's Word document are not part of the Phase 3 commits. `git lfs ls-files` identifies only the official `data/processed/hospital_discharges_clean.parquet` for the cleaned dataset.

## Known limitations

- Only 2021 data exists, so cross-year trends remain unavailable by design.
- Global cold MySQL aggregates remain OLAP scans and can take 0.6–8.7 seconds individually, longer under concurrent cold load.
- ECharts remains a 559.87 kB lazy shared chunk and triggers Vite's 500 kB advisory.
- Redis uses port 6380 in this acceptance environment because an existing local Redis owns 6379; configuration remains environment-driven.
- The cost model has R² 0.2301 and should not be used for individual financial, clinical or medical decisions.
- Windows/WSL2 compatibility was statically audited and documented, not physically tested in this macOS environment.
