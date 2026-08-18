# Phase 3A Performance After Redis Cache

Generated on 2026-08-18 against the same 2,094,483-row MySQL table. Each cold value is a real MySQL computation stored in a fresh Redis logical database; each hit immediately repeats the same repository call and asserts that the returned data is unchanged.

## Result comparison

| Query | Cold miss (ms) | Redis hit (ms) | Observed improvement |
|---|---:|---:|---:|
| overview | 2,186.75 | 0.43 | 99.98% |
| diseases_top | 1,909.49 | 0.50 | 99.97% |
| diseases_cost | 2,396.12 | 0.37 | 99.98% |
| hospitals_top | 5,039.93 | 0.78 | 99.98% |
| hospitals_cost | 4,947.21 | 0.51 | 99.99% |
| age_distribution | 7,050.00 | 0.59 | 99.99% |
| age_cost | 8,348.59 | 0.43 | 99.99% |
| payment_distribution | 634.43 | 0.45 | 99.93% |
| severity_distribution | 5,939.08 | 0.41 | 99.99% |
| yearly_trends | 3,087.19 | 0.34 | 99.99% |

These percentages compare a repeated cached request with a full aggregate and do not claim that MySQL itself became 99% faster. Cold-query variation reflects buffer/cache state and normal local-system load.

## Index decision

No new MySQL index was applied. The before plans show that the existing indexes are selected where useful, but metric-heavy global aggregates still process the full table. Adding low-selectivity or wide covering indexes was not justified by the plans and would trade disk/write cost for limited cold-query benefit. Consequently no `phase3_indexes.sql` migration is required.

## Runtime design

- Cache keys use canonical, sorted JSON of operation, filters, limit and metric, hashed under `medical:analytics:v1:<sha256>`.
- Default TTL is 300 seconds and is configurable.
- Only aggregate results are cached; raw hospital rows are never cached.
- Exceptions are never cached.
- Redis disabled/unavailable paths execute the original repository call and return normal API results.
- API/Tool telemetry reports `cache_hit`, `cache_miss`, `cache_disabled`, `cache_error` and `query_duration_ms`.

The reproducible cache profiler is `backend/scripts/profile_cache.py`.
