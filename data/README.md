# 数据目录

- `raw/`：放置唯一一份原始医疗数据（CSV、TSV 或 Parquet）。脚本只读该目录，不修改原文件。
- `processed/`：只保留最终清洗文件 `hospital_discharges_clean.parquet`，以及可选的小型聚合结果 `analytics_summary.json`。

患者级数据均被 `.gitignore` 排除。`.gitkeep` 仅用于保留目录结构。

当前仓库审计（2026-08-18）未检测到 README 所描述的 SPARCS 原始数据；请将已有文件直接放入 `data/raw/`，不要复制多份或更改文件名。脚本会按表头自动识别。
