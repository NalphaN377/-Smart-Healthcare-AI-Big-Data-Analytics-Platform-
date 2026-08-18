# Phase 3 Frontend Performance

Generated on 2026-08-18 with Vite 8.2.0. Both measurements are production builds from the same Phase 3 feature set.

## Before route splitting

| Asset | Minified | Gzip |
|---|---:|---:|
| Initial JavaScript bundle | 675.70 kB | 233.32 kB |
| CSS | 10.78 kB | 2.89 kB |

All four views and ECharts were reachable from the initial JavaScript graph.

## After route splitting

| Asset/chunk | Minified | Gzip |
|---|---:|---:|
| Initial application JavaScript | 89.49 kB | 34.87 kB |
| Dashboard view | 8.05 kB | 3.32 kB |
| AI Chat view | 7.40 kB | 3.73 kB |
| Data Quality view | 5.76 kB | 2.67 kB |
| Cost Prediction view | 5.03 kB | 2.46 kB |
| Shared ECharts chunk | 559.87 kB | 189.81 kB |
| CSS | 10.78 kB | 2.89 kB |

The initial minified JavaScript fell by 586.21 kB (86.76%). Dashboard, AI Chat, Data Quality and Cost Prediction now use Vue Router dynamic imports. ECharts was already registered through `echarts/core` with only Bar, Line, Pie and required components, so it remains a shared lazy chunk rather than entering the initial application bundle.

## Runtime finding

On a completely cold cache, several concurrent 2.09-million-row dashboard aggregates can exceed 15 seconds even though the backend succeeds. The finite frontend request timeout was changed from 15 to 45 seconds. Redis keeps repeat aggregate requests in the low-millisecond range; the higher first-load timeout avoids a false error while retaining bounded failure handling.

## Remaining limitation

The shared ECharts chunk is 559.87 kB minified and still triggers Vite's 500 kB warning. Further reduction would require a chart-library or renderer trade-off. Phase 3 keeps the proven ECharts implementation and prioritizes route-level first-load separation.
