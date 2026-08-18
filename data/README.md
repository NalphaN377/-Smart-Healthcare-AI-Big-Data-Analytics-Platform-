# 数据目录

- `raw/`：推荐放置唯一一份原始医疗数据（CSV、TSV 或 Parquet）。脚本也会递归识别仓库内其他嵌套位置，不要求复制或移动用户已有文件；原文件始终只读。
- `processed/`：本轮只保留最终清洗文件 `hospital_discharges_clean.parquet`。Spark 验证用的小型聚合结果应输出至系统临时目录并在验证后删除。

患者级数据均被 `.gitignore` 排除。`.gitkeep` 仅用于保留目录结构。

当前数据位于仓库根目录下的 `009 医养项目数据/` 嵌套目录，已由递归表头扫描识别。该目录与 SPARCS 文件名模式均被 `.gitignore` 排除。
