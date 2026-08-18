# 智慧医疗大数据与 AI 大模型分析平台

第一阶段 MVP：将真实住院出院数据经过分块探查、Pandas 清洗、Parquet 存储、MySQL 批量入库和 PySpark/Python 聚合，通过 Flask REST API 提供给 Vue 3 + ECharts 中文驾驶舱。

> 当前数据状态（2026-08-18）：仓库审计未找到 README 旧版所述的 SPARCS 原始数据。代码链路已使用明确隔离的 5 行测试夹具完成运行验证，但仓库中没有真实数据，因此不能给出或声称完整真实数据统计。将已有数据文件放到 `data/raw/` 后，按本文命令即可执行完整流程。

## 系统架构

```text
CSV / TSV / Parquet（只读原始数据）
        ↓ 分块读取、字段自动映射
Pandas 探查与清洗
        ↓ 单一 Zstandard Parquet
MySQL hospital_discharges
        ↓ SQL 聚合 / PySpark local[*]
Flask REST API
        ↓ 统一 JSON 契约
Vue 3 + ECharts 驾驶舱
```

Hadoop/HDFS、Hive、LangChain 和 LLM 仅保留 Phase 2 扩展边界，本阶段不部署集群或付费模型。

## 技术栈

- macOS / Apple Silicon；Python 3.11、Pandas、PyArrow、PySpark local mode。
- MySQL 8.4 官方多架构 Docker 镜像；PyMySQL 批量入库。
- Flask Application Factory、Flask-CORS、pytest。
- Vue 3、Vite、ECharts；无大型 UI 框架。

## 目录结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/                 # REST 端点与参数校验
│   │   ├── ai/                  # Phase 2 AI Provider 协议
│   │   ├── repositories/        # 参数化 MySQL 查询
│   │   ├── services/            # 业务服务层
│   │   └── utils/               # 字段映射、分块 IO、清洗规则
│   ├── scripts/                 # 探查、清洗、建库、导入、验证
│   ├── sql/schema.sql
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
├── frontend/                    # Vue 3 + ECharts
├── spark/jobs/medical_analytics.py
├── data/
│   ├── raw/                     # 原始数据，只读且不入 Git
│   └── processed/               # 唯一清洗 Parquet 与小型聚合 JSON
├── docs/                        # 数据报告和原有项目文档
├── docker-compose.yml
└── Makefile
```

## 环境要求

- **macOS** 13+（本项目不要求 Ubuntu、VMware 或 Linux VM）。
- Python 3.11+。
- Java 17 与 Spark 4.x；已有 `spark-submit` 时不要再安装重复 PySpark。
- Node.js：建议 22.18 LTS 或 24.11+；本机 Node 23.11 已实际构建成功，但部分最新传递依赖会给出非 LTS engine 警告。
- Docker Desktop（仅用于正式按 Compose 启动 MySQL）。若本机已有独立 MySQL，也可通过环境变量连接。
- 建议至少 8GB RAM；原始数据、Parquet 和 MySQL volume 需要足够磁盘。

本次审计环境：macOS 15.6.1 arm64、Python 3.11.3、Java 17、Spark 4.1.1、Node 23.11.0。Docker 未安装；Homebrew MySQL 9.3 临时实例已用于 SQL 兼容性验证。

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

将已有的唯一一份 CSV、TSV 或 Parquet 放入：

```text
data/raw/
```

不要重命名、编辑或复制多份原始文件。脚本会根据表头自动选择医疗字段匹配最多的文件，并处理 BOM、大小写、空格、下划线、CSV/TSV 分隔符及常见编码差异。

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

## PySpark local mode

```bash
spark-submit --master 'local[*]' spark/jobs/medical_analytics.py
```

输入清洗 Parquet，输出小型 `data/processed/analytics_summary.json`，完成总体指标、疾病 Top、疾病费用、年龄、医院、支付方式、严重程度和年度/疾病趋势。数据只有单一年份时，结果明确返回 `available: false`，不会制造年份。

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

当前共 13 个测试，覆盖字段/类型、费用非负、住院天数、出生体重、完全去重、主要 API、参数错误和 AI 预留端点。`backend/tests/fixtures/medical_sample.csv` 仅用于自动测试，不会被生产脚本自动发现，也不替代真实数据。

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
| POST | `/api/ai/query` | Phase 2 预留，当前返回 501 |

疾病数据不含患者唯一标识，因此接口准确表述为“住院记录数”，不伪称去重患者数。

## 当前功能与验证状态

- 数据探查与无数据阻塞报告：已实际运行。
- 分块清洗/Parquet/验证：已用隔离夹具实际运行，5 → 4 条，删除 1 条完全重复。
- MySQL 表、8 个业务/唯一索引、批量导入和幂等重跑：已用临时本机 MySQL 实际运行。
- Spark 8 类分析：已在 Spark 4.1.1 `local[*]` 实际运行。
- Flask 真实 SQL API、HTTP curl：已实际运行。
- pytest：13/13 通过。
- Vue production build：成功。
- 浏览器联调：7 个 canvas、0 个页面错误、0 个控制台 warning/error；390px 无水平溢出。
- Docker Compose：配置已提供，但当前机器没有 Docker，未声称容器启动成功。
- 完整真实 SPARCS 清洗、导入与统计：因原始数据文件缺失而未运行。

## Git 与磁盘安全

`.env`、虚拟环境、缓存、日志、`node_modules`、`dist`、Spark 临时目录以及 `data/raw/*` / `data/processed/*` 均被忽略，仅保留 `.gitkeep` 与 `data/README.md`。不要用 `git add -f data/raw/...`。项目不会下载第二份数据，也不会生成多版 CSV。

## 常见问题

### `No CSV, TSV or Parquet dataset found`

确认已有文件位于 `data/raw/`，不是 Finder `.textClipping`。不要把测试夹具移入生产数据目录。

### `docker: command not found`

安装 macOS Docker Desktop 后重新打开终端；本项目不要求 Ubuntu VM。若暂时使用本机 MySQL，设置 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`。

### MySQL `Access denied`

确认 `.env` 与当前容器 volume 的初始化密码一致。修改 `.env` 不会自动重置已有 MySQL volume；不要在未确认数据可删除时清空 volume。

### Spark 无法启动

确认 `java -version` 为 Java 17、`spark-submit --version` 可用。本项目不启动多节点 Spark/Hadoop。

### 页面显示数据服务异常

依次检查 `/api/health`、Flask 输出和 MySQL 健康状态；前端不使用假数据降级。

## 后续规划（Phase 2）

- HDFS、Hive 与 Spark 分布式化；
- LangChain Agent、LLM Tool Calling、多轮对话；
- 智能图表生成；
- Redis 缓存与任务队列。

这些组件当前未部署，避免额外镜像、缓存和磁盘占用。
