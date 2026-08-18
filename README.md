# 智慧医疗大数据与 AI 大模型分析平台

项目已完成 Phase 1 业务 MVP 和 Phase 2A 单机大数据环境：真实住院数据经过分块探查、Pandas 清洗和单一 Parquet 存储，同时进入 MySQL 业务查询链路与 HDFS/Hive/Spark 离线分析链路，最后由 Flask REST API 和 Vue 3 + ECharts 提供中文驾驶舱。

> 当前数据状态（2026-08-18）：已从仓库根目录递归识别用户原有的 2021 SPARCS CSV（2,101,588 行、33 字段、793.81 MiB），清洗为 2,094,483 行、37 字段的正式 Parquet。MySQL、Local Parquet、HDFS、Hive、Spark 和 API 的记录数均为 2,094,483，医疗机构数均为 205；原始数据未移动、复制或修改。

## 系统架构

```text
原始 CSV（只读）
        ↓ Pandas 分块清洗
Local cleaned Parquet（唯一正式版本）
        ├──→ MySQL hospital_discharges ──→ Flask API ──→ Vue + ECharts
        │       高频交互查询
        ├──→ HDFS（replication=1） ──→ Hive EXTERNAL TABLE
        │                                      ↓
        └──→ Spark local[*]（local / HDFS 可配置）←── Hive Metastore
                大规模聚合、离线分析和交叉验证
```

统一统计口径：**医疗机构数量 = 清洗后非空 `facility_name` 的区分大小写 distinct 数量**。该指标不使用 `facility_id` 回退，避免脱敏机构名称与数字 ID 混合计数。

Phase 2A 仅部署 1 个 NameNode 和 1 个 DataNode，Spark 仍为 `local[*]`；不部署多节点 Spark/Hadoop 集群。LangChain、LLM、Tool Calling、Redis 和多轮对话属于 Phase 2B，当前未实现。

## 技术栈

- macOS / Apple Silicon；Python 3.11、Pandas、PyArrow、PySpark local mode。
- Hadoop 3.4.3 HDFS、Hive 4.1.0 Metastore/Server2、Spark 4.1.1，均使用官方 ARM64 镜像。
- MySQL 8.4 官方多架构 Docker 镜像；PyMySQL 批量入库。
- Flask Application Factory、Flask-CORS、pytest。
- Vue 3、Vite、ECharts；无大型 UI 框架。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/                 # REST 端点与参数校验
│   │   ├── ai/                  # Phase 2B AI Provider 协议
│   │   ├── repositories/        # 参数化 MySQL 查询
│   │   ├── services/            # 业务服务层
│   │   └── utils/               # 字段映射、分块 IO、清洗规则
│   ├── scripts/                 # 探查、清洗、建库、导入、验证
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

- **macOS** 13+（本项目不要求 Ubuntu、VMware 或 Linux VM）。
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
docker compose up -d mysql
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

验证包括 HDFS report/文件可读性、Hive 全量记录与五类业务查询、Spark 从 HDFS 复用八类分析，以及 Spark SQL 通过 Hive Metastore 4.1 读取外部表。预期硬性结果是 2,094,483 行和 205 家非空医疗机构。Spark-Hive 首次运行需临时解析 Hive 4.1 client jars，会比 HDFS Parquet 直读慢；缓存位于一次性容器 `/tmp`，容器 `--rm` 后不长期占用磁盘。

### 停止、重启与持久化

```bash
scripts/bigdata/stop_bigdata.sh
scripts/bigdata/start_bigdata.sh
```

`stop_bigdata.sh` 只停止 HiveServer2、Hive Metastore、DataNode 和 NameNode，不停止 MySQL。以下 Docker 命名卷保留数据：

- `mysql_data`：Phase 1 业务表；
- `namenode_data`：HDFS 元数据；
- `datanode_data`：HDFS 单副本 Parquet block；
- `hive_metastore_data`：Hive Derby 元数据。

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

默认监听 `http://127.0.0.1:5000`。健康检查：

```bash
curl http://127.0.0.1:5000/api/health
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

## 前端启动

```bash
cd frontend
npm run dev
```

访问 `http://127.0.0.1:5173`。开发代理将 `/api` 转发到 Flask；也可在 `frontend/.env` 设置：

```text
VITE_API_BASE_URL=http://127.0.0.1:5000/api
```

驾驶舱包含 4 个总体指标，以及疾病 Top10、年龄分布、医疗费用、医院排行、支付方式、病情严重程度和年度趋势 7 个 ECharts 图表。所有统计均来自 API，并包含 Loading、Empty、Error 和移动端布局。

生产构建：

```bash
cd frontend
npm run build
```

## 测试

```bash
.venv/bin/python -m pytest -q
```

当前共 18 个测试，覆盖递归数据发现、字段/类型、费用非负、住院天数、出生体重、完全去重、统一机构计数口径、主要 API、参数错误、AI 预留端点、HDFS 单副本配置、Hive 外部表合约和 Hive 机构数口径。`backend/tests/fixtures/medical_sample.csv` 仅用于自动测试，不会被生产脚本自动发现，也不替代真实数据。

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
| POST | `/api/ai/query` | Phase 2B 预留，当前返回 501 |

疾病数据不含患者唯一标识，因此接口准确表述为“住院记录数”，不伪称去重患者数。

## 当前功能与验证状态

- 数据探查：已对 793.81 MiB、2,101,588 行真实 CSV 分 43 块运行，33/33 字段映射成功。
- 分块清洗/Parquet/验证：真实数据 2,101,588 → 2,094,483 行，删除 7,105 条完全重复；最终 Parquet 102.78 MiB。
- MySQL 表、业务/唯一索引、批量导入和幂等重跑：首次插入 2,094,483 行；第二次跳过 2,094,483 行且未重复写入。
- Spark 8 类分析：已在 Spark 4.1.1 `local[*]` 对完整 Parquet 实际运行。
- Flask 真实 SQL API：11 个 GET 端点均由 curl 验证为 HTTP 200，AI 预留端点按设计返回 501。
- pytest：18/18 通过。
- Vue production build：成功。
- 浏览器联调：4 个真实总体指标和 6 个 ECharts 成功加载，0 个控制台 warning/error；年度趋势因仅有 2021 年而显示真实 Empty 状态。
- 一致性核验：原始 profiling、清洗 Parquet、Spark、MySQL 和 API 的医疗机构数统一为 205。
- Docker Compose：MySQL 8.4 容器在 `127.0.0.1:3307` 通过 health check；完整导入后的 `COUNT(*)` 为 2,094,483。
- HDFS：NameNode/DataNode healthy，仅 1 个 107,773,178 字节 Parquet block，`replication=1`，`fsck` 为 HEALTHY。
- Hive：`medical_analytics.hospital_discharges` 外部表返回 2,094,483 行和 205 家机构，疾病、费用、支付和严重程度查询已实际运行。
- Spark HDFS：同一八类分析在 `local[*]` 下耗时 9.51 秒，Rows=2,094,483，Facility Count=205；Spark SQL 经 Hive Metastore 交叉读取也通过。
- Phase 2A 回归：pytest 18/18，Vue production build 成功，真实 `/api/overview` 仍为 2,094,483 / 205。

## Git 与磁盘安全

`.env`、虚拟环境、缓存、日志、`node_modules`、`dist`、Spark 临时目录以及 `data/raw/*` / `data/processed/*` 均被忽略，仅保留 `.gitkeep` 与 `data/README.md`。不要用 `git add -f data/raw/...`。HDFS/Hive 数据位于 Docker 命名卷，不在 repository 内。项目不会下载第二份原始数据，也不会生成多版 CSV/Parquet。

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

## 后续规划（Phase 2B）

- LangChain Agent、LLM Tool Calling、多轮对话；
- 智能图表生成；
- Redis 缓存与任务队列。

进入 Phase 2B 前应继续保留 MySQL 作为 Flask 交互查询层，HDFS/Hive/Spark 作为离线分析层；不应让每个 API 请求实时全表扫描 HDFS。Phase 2B 组件当前均未部署。
