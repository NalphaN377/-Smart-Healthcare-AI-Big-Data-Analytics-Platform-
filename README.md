# 智慧医疗大数据与 AI 大模型分析平台

项目已完成 Phase 1 业务 MVP、Phase 2A 单机大数据环境、Phase 2B AI 智能交互与 Phase 3 工程强化：真实住院数据经过分块探查、Pandas 清洗和单一 Parquet 存储，进入 MySQL 实时查询与 HDFS/Hive/Spark 离线分析链路；Redis 提供可降级的聚合缓存与 AI 会话持久化；Flask、LangChain 受控 Tool Calling、可替换 LLM Provider、scikit-learn 和 Vue 3 + ECharts 提供驾驶舱、数据质量、费用估计与多轮 AI 分析页面。

> 当前数据状态（2026-08-18）：已从仓库根目录递归识别用户原有的 2021 SPARCS CSV（2,101,588 行、33 字段、793.81 MiB），清洗为 2,094,483 行、37 字段的正式 Parquet。MySQL、Local Parquet、HDFS、Hive、Spark 和 API 的记录数均为 2,094,483，医疗机构数均为 205；原始数据未移动、复制或修改。

## 系统架构

```text
原始 CSV（只读） → Pandas 分块清洗 → cleaned Parquet（唯一正式版本）
                                         │
                    ┌────────────────────┴────────────────────┐
                    ↓                                         ↓
             MySQL hospital_discharges                 HDFS（replication=1）
                    ↓                                         ↓
             Analytics Service                         Hive EXTERNAL TABLE
               ↙            ↘                                ↓
   Redis analytics cache     AI Tool Layer ← LLM       Spark local[*]
                               ↑                       离线分析/交叉验证
                     Redis AI session store
                               ↓
             Flask API → Vue + ECharts / AI Chat

cleaned Parquet → 数据质量快照生成器 → 轻量 JSON → Data Quality API/Dashboard
cleaned Parquet → 可复现采样训练 → sklearn 模型 → Cost Prediction API/Page
```

统一统计口径：**医疗机构数量 = 清洗后非空 `facility_name` 的区分大小写 distinct 数量**。该指标不使用 `facility_id` 回退，避免脱敏机构名称与数字 ID 混合计数。

Phase 2A 仅部署 1 个 NameNode 和 1 个 DataNode，Spark 仍为 `local[*]`；不部署多节点 Spark/Hadoop 集群。交互查询继续使用 MySQL，不让每次 AI 提问触发 Spark/HDFS 全表扫描。Redis 是可选加速层；关闭或不可连接时 Analytics 与 AI 会话自动降级。本地大模型与 Spark Cluster 未部署。

## 技术栈

- macOS / Apple Silicon；Python 3.11、Pandas、PyArrow、PySpark local mode。
- Hadoop 3.4.3 HDFS、Hive 4.1.0 Metastore/Server2、Spark 4.1.1，均使用官方 ARM64 镜像。
- MySQL 8.4、Redis 7.4 官方多架构 Docker 镜像；PyMySQL 批量入库、redis-py。
- Flask Application Factory、Pydantic 2、LangChain 1、OpenAI-compatible Provider、scikit-learn、Flask-CORS、pytest。
- Vue 3、Vite、ECharts；无大型 UI 框架。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/                 # REST 端点与参数校验
│   │   ├── ai/                  # Agent、Provider、Tools、会话、ChartSpec
│   │   ├── cache/               # Redis client、聚合缓存与安全降级
│   │   ├── repositories/        # 参数化 MySQL 查询
│   │   ├── services/            # 业务服务层
│   │   └── utils/               # 字段映射、分块 IO、清洗规则
│   ├── scripts/                 # 探查、清洗、建库、导入、验证
│   ├── ml/                      # 费用模型训练、元数据与推理服务
│   ├── sql/schema.sql
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
├── frontend/                    # Vue 3 + ECharts
├── spark/jobs/
│   ├── medical_analytics.py      # local/HDFS 复用同一套八类分析
│   └── verify_hive.py            # Spark SQL 经 Hive Metastore 验证
├── docker/
│   ├── hadoop/                   # HDFS 配置与轻量派生镜像
│   ├── hive/                     # Hive 配置、DDL 和验证 SQL
│   └── spark/                    # Spark 工具镜像
├── scripts/bigdata/              # 启停、上传、建表和全链路验证
├── data/
│   ├── raw/                     # 原始数据，只读且不入 Git
│   └── processed/               # 唯一正式清洗 Parquet
├── docs/                        # 数据报告和原有项目文档
├── docker-compose.yml
└── Makefile
```

## 环境要求

- **macOS** 13+ 是当前完整实测平台（不要求 Ubuntu、VMware 或 Linux VM）。
- Windows 10/11 通过 Docker Desktop + WSL2 作为推荐兼容路径；见“Windows / WSL2”章节。
- Python 3.11+。
- Java 17 与 Spark 4.x；已有 `spark-submit` 时不要再安装重复 PySpark。
- Node.js：建议 22.18 LTS 或 24.11+；本机 Node 23.11 已实际构建成功，但部分最新传递依赖会给出非 LTS engine 警告。
- Docker Desktop / Docker Compose，用于 MySQL 以及 Phase 2A HDFS/Hive 服务。若本机已有独立 MySQL，请为项目 MySQL 保留不同宿主机端口（本次为 3307）。
- 建议至少 8GB RAM；原始数据、Parquet 和 MySQL volume 需要足够磁盘。

本次全量验证环境：macOS 15.6.1 arm64、16 GiB RAM，Python 3.11.3、Java 17、Spark 4.1.1、Node 23.11.0、Docker 29.7.2 / Compose 5.4.0。MySQL 8.4 容器通过 health check，并由本地 `.env` 配置映射至 `127.0.0.1:3307`；不会占用或停止本机 3306 服务。

## 安装

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt

cd frontend
npm install
cd ..

cp .env.example .env
```

编辑 `.env`，至少替换 `MYSQL_PASSWORD` 与 `MYSQL_ROOT_PASSWORD`。`.env` 已忽略，禁止提交。

若系统没有 Spark：

```bash
.venv/bin/python -m pip install -r spark/requirements.txt
```

## 数据准备

脚本会从 Git 仓库根目录递归查找 CSV、TSV 或 Parquet；已有数据不需要移动或复制。推荐的新数据位置仍为：

```text
data/raw/
```

不要重命名、编辑或复制多份原始文件。扫描会跳过 `.git`、`.venv`、`node_modules`、`dist`、缓存、测试夹具和 `data/processed`，再根据表头映射覆盖率和文件大小选择真实数据；支持 BOM、大小写、空格、下划线、CSV/TSV 分隔符及常见编码差异。本次数据保留在 `009 医养项目数据/` 的原有嵌套路径中。

统一内部字段包括 `facility_id`、`facility_name`、`age_group`、`length_of_stay`、`diagnosis_code`、`diagnosis_description`、`severity`、`payment_type_1`、`birth_weight`、`emergency_indicator`、`total_charges`、`total_costs` 等。CCS/CCSR 的常见旧字段名均有别名映射；缺失字段会在报告中明确标注，不会伪造。

### 数据探查

```bash
.venv/bin/python backend/scripts/inspect_data.py
```

输出 `docs/data_profile.md`，含文件大小、准确行数、字段映射、缺失率、受限内存的唯一值统计、数值统计、分类 Top 值、重复估算和异常计数。默认每块 50,000 行，不一次性载入全量数据。

### 数据清洗

```bash
.venv/bin/python backend/scripts/clean_data.py
.venv/bin/python backend/scripts/validate_data.py
```

默认只生成：

```text
data/processed/hospital_discharges_clean.parquet
```

清洗采用临时文件 + 原子替换，并用磁盘型哈希索引处理跨块完全重复记录。已有输出不会被默认覆盖；明确重跑时使用 `--overwrite`。主要规则：

- 金额移除 `$`、逗号和空白，非法或负值转 NULL。
- `120+` 住院天数标准化为 120，同时保留 `length_of_stay_raw`；负数和明显异常值转 NULL。
- 非 Newborn/Neonate 上下文的出生体重、0 或大于 15,000g 的值转 NULL。
- 分类字段仅清理 Unicode、控制字符、重复空白和空值，不合并医学类别。
- 出院年份限定 1900 至当前年份 + 1；急诊指标统一为 true/false/NULL。
- 质量报告写入 `docs/data_quality_report.md`。

如需在全量清洗前验证规则，可使用受限行数输出到系统临时目录，例如 `--max-rows 50000`；不要在项目中保留多份预运行数据。

## 数据库启动与导入

1. 启动官方 MySQL 8.4：

```bash
docker compose up -d mysql redis
docker compose ps
```

2. 建表并批量导入：

```bash
.venv/bin/python backend/scripts/init_database.py
.venv/bin/python backend/scripts/import_data.py
```

导入按 2,000 行批事务提交；失败批次自动二分定位到源行，不逐行 commit。`record_hash` 唯一索引使同一 Parquet 重跑幂等。脚本最终输出 Imported/Existing/Failed rows、耗时、吞吐、`SELECT COUNT(*)` 和 Parquet 行数。

表 `hospital_discharges` 使用 BIGINT/INT/DECIMAL/BOOLEAN/VARCHAR 等明确类型。索引仅覆盖：

- `facility_id`、`facility_name`：医院排行与筛选；
- `age_group`、`discharge_year`：年龄/年度聚合；
- `diagnosis_code`、`severity`、`payment_type_1`：疾病、严重程度与支付分析；
- `record_hash`：精确去重与幂等导入。

没有为低频展示字段创建索引，以控制 200 万级记录的写入和磁盘成本。

## Redis 缓存与 AI 会话

Redis 7.4 使用官方多架构镜像、AOF `everysec`、healthcheck、日志轮转和 `redis_data` 命名卷，只绑定 `127.0.0.1`。默认端口 6379；若宿主机已有 Redis，可在本地 `.env` 设置其他端口，例如 `REDIS_PORT=6380`，无需停止现有服务。

```text
REDIS_ENABLED=true
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_CACHE_TTL=300
REDIS_SESSION_TTL=86400
```

Analytics 缓存只保存聚合结果，不保存原始病历行。key 由 Tool/API、排序后的 filters、limit 和 metric 生成稳定 SHA-256；默认 TTL 300 秒。`GET /api/system/cache/status` 仅返回 enabled、connected、backend 和 ttl，不暴露 URI 或凭据。

AI 会话使用 `RedisConversationStore` 保存最多 10 轮的小型问题、Tool 参数和摘要；Flask 重启后仍可恢复。Redis 禁用或不可连接时，聚合查询直接回源 MySQL，会话自动回退到 `InMemoryConversationStore`，API contract 不变。不要执行 `docker compose down -v`，否则会删除命名卷。

MySQL 8.4 的 `EXPLAIN ANALYZE` 显示：固定 Dashboard 的全局分组仍需消费 2,094,483 行。现有紧凑维度索引已在合适查询中使用，Phase 3 没有添加低选择性或宽 covering index。实测 Redis hit 为 0.34–0.78 ms，而对应冷聚合为 0.63–8.35 秒；详见 `docs/sql_performance_before.md` 与 `docs/sql_performance_after.md`。

## 数据质量 Dashboard

以下命令从正式 cleaned Parquet 流式生成轻量机器可读快照，不在打开页面时扫描 209 万行：

```bash
.venv/bin/python backend/scripts/generate_data_quality_metrics.py
```

快照为 `docs/data_quality_metrics.json`，页面路径为 `/data-quality`。当前实测：2,094,483 行、37 列、205 家机构，完整性 92.04%、有效性 100%、一致性 100%；诊断描述缺失 1,634 条、严重程度缺失 2,548 条，其余列出的关键字段无缺失。异常规则结果和生成时间均由后端 API 返回，前端不硬编码真实指标。

## 住院费用估计

训练目标为 `total_costs`。模型明确排除 `total_costs`、`total_charges`、`length_of_stay`、来源元数据、行号和 hash；输入只使用年龄组、性别、入院类型、CCSR 诊断代码、严重程度、死亡风险、医疗/外科分类、急诊标志和第一支付方式。

```bash
.venv/bin/python backend/ml/train_cost_model.py
```

训练脚本流式读取正式 Parquet，默认以固定随机种子从全文件选择 200,000 行，按 160,000/40,000 划分训练/测试，并训练 `OrdinalEncoder + log-target HistGradientBoostingRegressor`。正式实测：MAE 12,461.03、RMSE 38,134.04、R² 0.2301，中位数基线 MAE 15,863.92。joblib 工件默认位于 `backend/ml/artifacts/` 且被 Git 忽略；模型元数据和限制记录在 `docs/ml_cost_prediction_report.md`。

模型状态与推理页面分别为 `/api/ml/cost-prediction/status`、`/api/ml/cost-prediction/predict` 和 `/cost-prediction`。模型未训练时 status 明确 unavailable，predict 返回安全的 503。该功能仅用于数据分析和教学展示，不构成医疗建议、临床决策或费用结算依据。

## Phase 2A 单机大数据环境

Phase 2A 在原有 Compose 项目中增量加入以下服务，不重建 `mysql_data`，不改变项目 MySQL 的 3307 映射：

| Service | 镜像/版本 | 宿主机端口 | 内存上限 | 职责 |
|---|---|---:|---:|---|
| `mysql` | `mysql:8.4` | 3307 | Docker Desktop 全局限额 | Flask 高频业务查询 |
| `namenode` | Hadoop 3.4.3 | 8020 / 9870 | 768 MiB | HDFS 元数据和 Web UI |
| `datanode` | Hadoop 3.4.3 | 9864 | 1 GiB | 单节点 HDFS 数据块 |
| `hive-metastore` | Hive 4.1.0 standalone | 9083 | 768 MiB | 独立 Derby 元数据，不污染业务 MySQL |
| `hiveserver2` | Hive 4.1.0 | 10001 → 10000 | 1.5 GiB | Beeline / Hive SQL |
| `spark-client` | Spark 4.1.1 Python 3 | 不发布 | 2 GiB | 一次性 `local[*]` 分析工具，不是 Spark Cluster |

选用官方多架构镜像 `ghcr.io/apache/hadoop:3.4.3`、`apache/hive:4.1.0`、`apache/hive:standalone-metastore-4.1.0` 和 `apache/spark:4.1.1-python3`，实际镜像架构均验证为 ARM64。项目派生镜像只 COPY 配置、SQL 和 Spark job，不 COPY 原始 CSV 或 Parquet。

### 启动和健康检查

```bash
scripts/bigdata/start_bigdata.sh
docker compose --profile bigdata ps
```

启动顺序由 `service_completed_successfully` 和 `service_healthy` 编排，不依赖固定 `sleep`。NameNode UI 为 `http://127.0.0.1:9870`，DataNode UI 为 `http://127.0.0.1:9864`；容器间通过 `namenode`、`datanode`、`hive-metastore` 等 service name 通信。由于 macOS 的 10000 端口已被系统进程占用，HiveServer2 使用宿主机 10001；不停止无关系统服务。

### 上传唯一正式 Parquet

```bash
scripts/bigdata/upload_to_hdfs.sh
```

脚本将已有 `data/processed/hospital_discharges_clean.parquet` 通过标准输入流式写入：

```text
hdfs://namenode:8020/medical/processed/hospital_discharges/hospital_discharges_clean.parquet
```

脚本会比较本地与 HDFS 字节数，对同尺寸已有文件直接跳过，对尺寸不同或多版文件拒绝覆盖。HDFS 仅保留这一份约 102.8 MiB 的 cleaned Parquet，不上传 793.81 MiB 原始 CSV；`dfs.replication=1`。

### Hive 外部表

```bash
scripts/bigdata/init_hive.sh
```

Parquet metadata 实际显示 2,094,483 行、43 个 row group、37 列；`docker/hive/init.sql` 使用与该 schema 对应的 `STRING/BIGINT/BOOLEAN/DOUBLE`，创建：

```text
database: medical_analytics
external table: medical_analytics.hospital_discharges
location: hdfs://namenode:8020/medical/processed/hospital_discharges
external.table.purge: false
```

删除 Hive table 不会删除 HDFS Parquet。Hive 元数据保存在独立 `hive_metastore_data` 命名卷，不使用 `medical_platform` 业务数据库。

### 全链路验证

```bash
scripts/bigdata/verify_bigdata.sh
```

验证包括 HDFS report/文件可读性、Hive 全量记录与五类业务查询、Spark 从 HDFS 复用八类分析，以及 Spark SQL 通过 Hive Metastore 4.1 读取外部表。预期硬性结果是 2,094,483 行和 205 家非空医疗机构。

Spark-Hive 首次运行需要解析 279 个 Hive 4.1 client artifact。`spark_ivy_cache` 命名卷挂载到实际的 `/opt/spark/.ivy2.5.2`，因此一次性工具容器 `--rm` 后仍保留依赖。实际补齐缓存耗时 349.13 秒，随后完全热启动为 8.80 秒（Spark SQL 本体 5.40 秒）；不会再重复约 11 分钟的冷启动下载。

### 停止、重启与持久化

```bash
scripts/bigdata/stop_bigdata.sh
scripts/bigdata/start_bigdata.sh
```

`stop_bigdata.sh` 只停止 HiveServer2、Hive Metastore、DataNode 和 NameNode，不停止 MySQL。以下 Docker 命名卷保留数据：

- `mysql_data`：Phase 1 业务表；
- `namenode_data`：HDFS 元数据；
- `datanode_data`：HDFS 单副本 Parquet block；
- `hive_metastore_data`：Hive Derby 元数据；
- `spark_ivy_cache`：Spark→Hive Maven/Ivy 依赖，不含医疗数据。

**不要执行 `docker compose down -v`、`docker volume prune` 或 `docker system prune -a`。** 除非已明确决定删除所有 Docker 数据。HDFS/Hive 数据只在 Docker volume 中，不写入 Git 仓库。

## PySpark local mode

```bash
spark-submit --master 'local[*]' spark/jobs/medical_analytics.py --source local
```

本地模式读取 cleaned Parquet，并完成总体指标、疾病 Top、疾病费用、年龄、医院、支付方式、严重程度和年度/疾病趋势。HDFS 模式通过相同 `medical_analytics.py` 逻辑运行：

```bash
docker compose --profile tools run --rm --no-deps spark-client \
  /opt/spark/bin/spark-submit --master 'local[*]' \
  /opt/medical/jobs/medical_analytics.py \
  --source hdfs \
  --hdfs-uri hdfs://namenode:8020/medical/processed/hospital_discharges \
  --output /tmp/hdfs_medical_analytics.json
```

也可使用 `MEDICAL_SPARK_SOURCE=local|hdfs` 和 `MEDICAL_HDFS_URI`。若只需本地验证而不希望在项目内保留聚合文件，可用 `--output /private/tmp/medical_analytics.json`；真实数据仅包含 2021 年，结果明确返回 `available: false`，不制造年份。

## 后端启动

```bash
.venv/bin/python backend/run.py
```

默认监听 `http://127.0.0.1:5001`，避免 macOS Control Center 使用的 5000。健康检查：

```bash
curl http://127.0.0.1:5001/api/health
```

所有响应使用：

```json
{
  "success": true,
  "data": [],
  "meta": {
    "dimension": "disease",
    "metric": "record_count",
    "filters": {},
    "count": 10,
    "elapsed_ms": 12.5
  },
  "message": null
}
```

错误只返回安全消息，不向前端泄露 traceback。支持 `limit`（1–100）、`year`、`age_group`、`hospital` 和 `diagnosis`；未知或非法参数返回 HTTP 400。

## AI Architecture

```text
User / Vue AI Chat
        ↓ POST /api/ai/query
MedicalAnalyticsAgent
        ↓ Provider 只负责选择 allow-listed tool
LangChain structured tool calling
        ↓ Pydantic 参数校验（limit 1–50）
ToolRegistry → 现有 Service / Repository → MySQL
        ↓ 结构化真实结果
Provider 中文摘要 → GroundingGuard → deterministic ChartPlanner
        ↓
answer + tool_calls + sources + safe ChartSpec → Vue / ECharts
```

Agent 无权生成或执行任意 SQL，不连接 Shell/HDFS/Hive，不调用任意 URL，不读取或返回 `.env`。八个 Tool 仅复用现有 service/repository：

- `get_overview`
- `get_top_diseases`
- `get_disease_cost_analysis`
- `get_hospital_analysis`
- `get_age_analysis`
- `get_payment_distribution`
- `get_severity_analysis`
- `get_year_trend`

`get_year_trend` 会读取真实年份。当前只有 2021 年，因此明确返回跨年趋势不可用，并且不生成 line chart。图表仅允许 `bar`、`horizontal_bar`、`pie`、`line` 和 `table` 的 Pydantic `ChartSpec`；前端不执行模型生成的 JavaScript。

### 配置 Provider

默认 Provider 是 `openai_compatible`，可连接 DeepSeek、Qwen 或其他 OpenAI-compatible 服务。DeepSeek V4 Flash 的 non-thinking 配置示例：

```text
AI_PROVIDER=openai_compatible
LLM_API_KEY=replace_locally
LLM_MODEL=deepseek-v4-flash
LLM_BASE_URL=https://api.deepseek.com
LLM_TIMEOUT_SECONDS=30
LLM_THINKING_MODE=disabled
AI_MAX_TURNS=10
```

以上值只写入本地 `.env`，禁止提交或记录 Key。`LLM_THINKING_MODE=disabled` 会在请求体中显式发送 non-thinking 配置；`GET /api/ai/status` 仅返回 Provider 名、model 与 thinking mode，不返回 Key 或 Base URL。Provider 未配置时 `POST /api/ai/query` 返回 HTTP 503，但 MySQL、HDFS、Hive、Spark、Dashboard 和全部普通 analytics API 继续运行。测试专用 `DeterministicTestProvider` 只能通过显式依赖注入或验证脚本使用，生产环境不会自动选择它。

### 多轮上下文与安全边界

`ConversationStore` 默认每个会话最多保留 10 轮，仅保存问题、Tool 名、已验证参数和最多 3 行结果摘要，不保存全量数据。Redis 可用时会话带 TTL 持久化；不可用时自动回退内存版。追问可继承 dimension、metric、top_k、`age_group`、`hospital` 和其他已有 filter。

摘要 Prompt 禁止创造数字/年份、编造医学因果、提供患者个体诊断建议或把住院记录数伪称独立患者人数。`GroundingGuard` 会检查数字、年份、费用/成本字段标签、分类名称和工具未提供的币种；任何一项不一致都会回退到确定性 Tool Result 表述。响应 meta 分别报告 routing、Tool/MySQL、summary、总耗时与 token usage。系统是数据分析与教学演示平台，不是医疗诊断系统。

请求示例：

```bash
curl -X POST http://127.0.0.1:5001/api/ai/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"住院人数最多的五种疾病是什么？"}'
```

成功响应包含 `answer`、实际 `tool_calls` 与参数、`sources`、安全 `chart`、`session_id`，以及 Provider/Tool/总耗时；不包含 chain-of-thought。错误口径为：参数/Tool 校验 400、unsupported query 422、Provider 未配置 503、Provider timeout 504、上游 Provider failure 502。

## 前端启动

```bash
cd frontend
npm run dev
```

访问 `http://127.0.0.1:5173`。开发代理将 `/api` 转发到 Flask；也可在 `frontend/.env` 设置：

```text
VITE_API_BASE_URL=http://127.0.0.1:5001/api
```

驾驶舱包含 4 个总体指标，以及疾病 Top10、年龄分布、医疗费用、医院排行、支付方式、病情严重程度和年度趋势 7 个 ECharts 区域。`/ai` 是响应式聊天页，`/data-quality` 展示离线质量快照，`/cost-prediction` 提供严格受控的模型输入和免责声明。四个主要页面均通过 Vue Router dynamic import 懒加载；初始 JS 从 675.70 kB 降至 89.49 kB。所有业务统计均来自 API，不含 fixture/mock 或前端硬编码结果。

生产构建：

```bash
cd frontend
npm run build
```

## 测试

```bash
.venv/bin/python -m pytest -q
```

当前共 78 个测试，覆盖原 Phase 1/2A 数据与 API 回归、Redis unavailable fallback/hit/miss/key/TTL/session、数据质量快照、ML schema/无泄漏/推理/不可用状态，以及 AI Tool allow-list、Agent 路由、3 类多轮上下文、GroundingGuard、token usage、ChartSpec、防任意 JavaScript、Provider 错误与医疗安全边界。测试 fixture 会显式注入未配置 Provider，不会受开发者本机 API Key 影响。`backend/tests/fixtures/medical_sample.csv` 仅用于自动测试，不会被生产脚本自动发现，也不替代真实数据。

连接真实 MySQL、使用明确标记为测试用途的 deterministic Provider 验证 10 个问题和 3 组追问：

```bash
.venv/bin/python backend/scripts/validate_ai_agent.py
```

该脚本不调用外部 LLM，也不伪装生产 Provider；它只验证自然语言路由、真实 analytics service 结果、grounding、ChartSpec 与多轮参数继承。HDFS/Hive/Spark 重型回归独立执行 `scripts/bigdata/verify_bigdata.sh`，不放入日常 pytest。

在明确配置真实 DeepSeek Provider 后，可运行包含 10 个问题和 3 组追问的真实验收（会产生外部 API 调用与相应 token 用量）：

```bash
.venv/bin/python backend/scripts/validate_deepseek_agent.py
```

## API 列表

| Method | Path | 功能 |
|---|---|---|
| GET | `/api/health` | API 与数据库健康状态 |
| GET | `/api/overview` | 总记录、机构、住院时长、费用、成本、急诊占比 |
| GET | `/api/diseases/top` | 疾病住院记录 Top |
| GET | `/api/diseases/cost` | 疾病平均费用/成本 |
| GET | `/api/hospitals/top` | 医院住院量 Top |
| GET | `/api/hospitals/cost` | 医院平均费用/成本/住院时长 |
| GET | `/api/age/distribution` | 年龄组记录数与住院时长 |
| GET | `/api/age/cost` | 年龄组费用/成本 |
| GET | `/api/payments/distribution` | 第一支付方式及全量占比 |
| GET | `/api/severity/distribution` | 严重程度、费用与住院时长 |
| GET | `/api/trends/year` | 年度住院量与费用趋势 |
| GET | `/api/system/cache/status` | Redis 缓存安全状态 |
| GET | `/api/data-quality/summary` | 数据质量总体快照 |
| GET | `/api/data-quality/fields` | 关键字段缺失率 |
| GET | `/api/ai/status` | Provider 配置状态（不返回 Key/Base URL） |
| POST | `/api/ai/query` | 受控 Tool Calling、grounded 中文洞察、ChartSpec、多轮会话 |
| GET | `/api/ml/cost-prediction/status` | 费用模型状态、特征与指标 |
| POST | `/api/ml/cost-prediction/predict` | 严格校验的住院费用估计 |

疾病数据不含患者唯一标识，因此接口准确表述为“住院记录数”，不伪称去重患者数。

## 当前功能与验证状态

- 数据探查：已对 793.81 MiB、2,101,588 行真实 CSV 分 43 块运行，33/33 字段映射成功。
- 分块清洗/Parquet/验证：真实数据 2,101,588 → 2,094,483 行，删除 7,105 条完全重复；最终 Parquet 102.78 MiB。
- MySQL 表、业务/唯一索引、批量导入和幂等重跑：首次插入 2,094,483 行；第二次跳过 2,094,483 行且未重复写入。
- Spark 8 类分析：已在 Spark 4.1.1 `local[*]` 对完整 Parquet 实际运行。
- Flask 真实 SQL API：12 个 GET 端点均由 curl 验证为 HTTP 200；未配置 LLM Key 时 AI query 按设计返回 503，普通 API 不受影响。
- AI 自然语言验证：10 个真实问题与 3 组多轮追问全部命中预期 Tool，数据来源均为 MySQL 全量 2,094,483 条记录。
- Redis：项目容器在本机已有 6379 服务的情况下使用 `127.0.0.1:6380`，health check 通过；聚合 hit telemetry 与跨进程会话恢复已实测。
- 数据质量：真实 Parquet 快照生成耗时 11.6 秒；API 与 `/data-quality` 图表/表格通过浏览器验证。
- 费用模型：200,000 行训练样本，训练 3.15 秒，MAE 12,461.03；状态、推理 API 和 `/cost-prediction` 实际交互通过。
- pytest：78/78 通过。
- Vue production build：成功；初始 JS 89.49 kB，四页懒加载。
- 浏览器联调：Dashboard、AI、Data Quality、Cost Prediction 均加载成功；真实费用推理返回，0 个控制台 warning/error。
- 一致性核验：原始 profiling、清洗 Parquet、Spark、MySQL 和 API 的医疗机构数统一为 205。
- Docker Compose：MySQL 8.4 容器在 `127.0.0.1:3307` 通过 health check；完整导入后的 `COUNT(*)` 为 2,094,483。
- HDFS：NameNode/DataNode healthy，仅 1 个 107,773,178 字节 Parquet block，`replication=1`，`fsck` 为 HEALTHY。
- Hive：`medical_analytics.hospital_discharges` 外部表返回 2,094,483 行和 205 家机构，疾病、费用、支付和严重程度查询已实际运行。
- Spark HDFS：同一八类分析在 `local[*]` 下最终耗时 11.16 秒，Rows=2,094,483，Facility Count=205；Spark SQL 经 Hive Metastore 交叉读取也通过。
- Spark→Hive cache：279 个 artifact 持久化，补齐缓存 349.13 秒，第二次热启动 8.80 秒，完整 `verify_bigdata.sh` 通过。
- Phase 3 回归：pytest 78/78、Vue production build、全部真实 HTTP、MySQL/Redis/HDFS/Hive/Spark 均通过；`/api/overview` 仍为 2,094,483 / 205。一次最小真实 DeepSeek 回归命中 `get_top_diseases(limit=5)`，没有生成 SQL 或 JavaScript。

## Git 与磁盘安全

`.env`、虚拟环境、模型工件、缓存、日志、`node_modules`、`dist`、Spark 临时目录以及未跟踪的 `data/raw/*` / `data/processed/*` 均被忽略。正式 `hospital_discharges_clean.parquet` 是唯一例外，已明确由 Git LFS 管理；不要用 `git add -f` 添加其他医疗数据。HDFS/Hive 数据位于 Docker 命名卷，不在 repository 内。项目不会下载第二份原始数据，也不会生成多版 CSV/Parquet。

## Windows 10/11 + WSL2

Windows 推荐通过 WSL2 执行 Python、Git、Make 与 Bash 脚本，并由 Docker Desktop 提供 Linux containers。该路径是 **supported by design / recommended deployment path**；完整端到端实测平台仍是 macOS Apple Silicon，不能表述为 Windows 已实测通过。

1. 安装 WSL2（推荐 Ubuntu 发行版，仅作为 Windows 的 WSL 用户空间）和 Docker Desktop，启用对应 WSL integration。
2. 将仓库放在 WSL 文件系统（如 `~/projects/medical-ai-platform`），避免 `/mnt/c` 上大量 Parquet/Node 小文件的 I/O 开销。
3. 在 WSL 终端执行本文 Bash 命令；不要从 PowerShell 直接运行 `scripts/bigdata/*.sh`。
4. 安装 Python 3.11+、Node LTS、Git LFS 和 Java 17；Docker 镜像不写死 arm64，官方镜像会选择 x86_64 变体。
5. 本地 `.env` 使用 `MYSQL_HOST=127.0.0.1` 及 Docker 映射端口。若 3306/6379 已占用，仅调整宿主端口，不修改容器内端口。

Python 路径均通过 `pathlib` 或仓库根目录动态解析，文档和代码不含开发者机器绝对路径。Compose 未设置固定 `platform`，命名卷与健康检查在 macOS/WSL2 采用同一配置。WSL2 仍应自行完成 `pytest`、`npm run build` 与全链路数据计数验收。

## 常见问题

### `No CSV, TSV or Parquet dataset found`

脚本会递归扫描仓库，但会主动排除测试夹具、生成数据和依赖目录。确认文件后缀为 CSV、TSV 或 Parquet 且当前用户可读；Finder `.textClipping` 不属于数据文件。

### Docker / Compose 无法连接

确认 macOS Docker Desktop 正在运行，再执行 `docker compose ps`。若 3306 已被本机 MySQL 使用，可像本次验证一样在 `.env` 中设置 `MYSQL_PORT=3307`；应用不会硬编码端口，也不要求停止本机服务。

### MySQL `Access denied`

确认 `.env` 与当前容器 volume 的初始化密码一致。修改 `.env` 不会自动重置已有 MySQL volume；不要在未确认数据可删除时清空 volume。

### Spark 无法启动

本机 local 模式确认 `java -version` 为 Java 17、`spark-submit --version` 可用。HDFS 模式请先检查 NameNode/DataNode healthy，再通过 Compose `spark-client` 运行；该客户端仍是 `local[*]`，不是多节点 Spark Cluster。

### HiveServer2 不在宿主机 10000 端口

本次 macOS 环境的 10000 已被系统进程占用，Compose 使用 `127.0.0.1:10001 -> container:10000`。容器内 Beeline 仍连接 `127.0.0.1:10000`，其他容器通过 service name 通信。

### 页面显示数据服务异常

依次检查 `/api/health`、Flask 输出和 MySQL 健康状态；前端不使用假数据降级。

### AI 页面显示 `AI provider not configured`

这是未配置 `LLM_API_KEY` 或 `LLM_MODEL` 时的预期安全状态。只在本地 `.env` 配置 Provider，不要修改 `.env.example` 写入真实 Key。该状态不会影响 Dashboard 和普通 analytics API。

## Phase 3 完成状态与后续边界

Phase 3 已完成 Redis 会话/聚合缓存、真实 SQL profiling、数据质量看板、无直接费用泄漏的费用估计、前端 route splitting、macOS 全链路验收与 WSL2 兼容性整理。已知限制：当前数据仅有 2021，无法形成跨年趋势；固定全局聚合的冷查询仍可能需要数秒；ECharts lazy chunk 仍约 560 kB；费用模型受行政数据特征和重尾目标限制，不应用于诊断、临床决策或结算。

后续可以评估 Redis 预热/监控、数据质量历史快照、模型解释和系统级性能优化，但本轮不引入 Kubernetes、Kafka、本地大模型或 Spark Cluster。
