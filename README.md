# 智慧医疗大数据与 AI 大模型分析平台

基于 2021 年 SPARCS 脱敏住院出院数据建设的一期完整实现，覆盖 33 字段数据治理、SQL Server 持久化、多维聚合分析、数据质量评估、DeepSeek V4 Flash 流式问答、洞察报告和 Vue 3 可视化大屏。

当前工作区已完成全量导入：原始 2,101,588 行，清洗去重后 2,094,418 行。

## 技术架构

```text
SPARCS CSV
  → Pandas / SQL Server BULK INSERT 清洗与校验
  → SQL Server（业务表、索引、导入审计）
  → Flask REST / SSE 分析服务
  → 规则意图识别 + DeepSeek Anthropic API
  → Vue 3 + ECharts 响应式运营大屏
```

主要目录：

```text
app/data_layer/                    数据读取、清洗、质量评估、SQL Server 存储
app/service_layer/                聚合分析、REST/SSE API、Flask 应用
app/ai_layer/                     意图识别、Agent、图表、DeepSeek 摘要与报告
frontend/                         Vue 3 前端
scripts/ingest.py                 通用 Pandas 分块导入
scripts/bulk_ingest_sqlserver.py  SQL Server 原生高速全量导入
sql/schema.sql                    SQL Server 表、索引和二期 staging 表
tests/                            单元、API 与真实数据库集成测试
```

## 本地运行

### 1. 后端环境

项目统一使用 Python 3.11，开发环境由 conda 环境 `hwadee` 管理（Python 3.11.15 + 全部依赖已就绪）。

```powershell
conda activate hwadee
Copy-Item .env.example .env   # 首次使用，随后填写本机密码与密钥
```

如 `hwadee` 环境缺失或需重建：

```powershell
conda create -n hwadee python=3.11 -y
conda activate hwadee
pip install -r requirements.txt
```

> 后文命令均假设已 `conda activate hwadee`；未激活时把 `python` 换成 `conda run -n hwadee python`。PyCharm 解释器请选本机 `hwadee` 环境下的 `python.exe`，路径用 `conda env list` 查看（例如 `E:\support\Anaconda3\envs\hwadee\python.exe`，各人机器不同）。

### 1.1 Spark 环境（仅运行 `scripts/spark_etl.py` 需要）

`pyspark` 已在 `requirements.txt` 中，但 Spark 在 Windows 上还需要 JDK 17 和 winutils，
否则会报 `UnsatisfiedLinkError: NativeIO$Windows.access0` 或 Python worker `Connection reset`。

```powershell
scoop install java/openjdk17 versions/hadoop-winutils33
```

然后设置以下用户环境变量（路径按本机实际安装位置调整）：

| 变量 | 值 | 作用 |
|---|---|---|
| `SPARK_JAVA_HOME` | JDK 17 根目录 | Spark 不支持 JDK 22+，脚本据此自动切换 |
| `HADOOP_HOME` | winutils 安装根目录 | 提供 `winutils.exe` 与 `hadoop.dll` |
| `PYSPARK_PYTHON` | `hwadee` 环境的 `python.exe` | 否则 JVM 会用 PATH 上的其它 Python 启动 worker 并崩溃 |
| `PYSPARK_DRIVER_PYTHON` | 同上 | 同上 |

还需确保 `%HADOOP_HOME%\bin`（含 `winutils.exe` 和 `hadoop.dll`）在 `PATH` 上，
否则 `hadoop.dll` 加载不到，`NativeCodeLoader.isNativeCodeLoaded()` 为 `false`，Parquet 写入会失败。

编辑 `.env`，至少填写：

```dotenv
DB_HOST=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=你的本机密码
DB_NAME=yiliaoBigData
DEEPSEEK_API_KEY=你的密钥
```

密钥与密码只放在已被 Git 忽略的 `.env` 或 PyCharm 运行环境变量中，不要提交到仓库。

### 2. 数据库与全量导入

创建空数据库 `yiliaoBigData` 后，可执行高速导入。脚本会初始化 Schema、BULK INSERT 到 staging 表、清洗转换、去重并记录质量审计。

```powershell
python scripts\bulk_ingest_sqlserver.py `
  --file "..\data\Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --truncate
```

小文件或非 SQL Server 原生导入场景也可使用：

```powershell
python scripts\ingest.py --file "..\data\your_file.csv" --init-schema
```

`--truncate` 会清空业务表，仅在明确需要重新全量导入时使用。

### 3. 启动后端和前端

终端一：

```powershell
python run.py
```

终端二：

```powershell
Set-Location frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 代理到 `http://127.0.0.1:5000`。

## 核心接口

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/api/health` | 数据库、LLM 与功能开关状态 |
| GET | `/api/overview` | 前端运营总览聚合数据 |
| GET | `/api/aggregate` | 白名单维度/指标通用聚合 |
| GET | `/api/avg_length_of_stay` | 平均住院日分析 |
| GET | `/api/cost_distribution` | 费用和成本分析 |
| GET | `/api/payment_ratio` | 支付方式占比 |
| GET | `/api/year_trend` | 年度趋势 |
| GET | `/api/data-quality` | 最近导入与四维质量报告 |
| POST | `/api/chat` | AI 非流式完整分析 |
| POST | `/api/chat/stream` | AI SSE 流式分析 |
| POST | `/api/reports` | Markdown 洞察报告 |
| GET/POST | `/api/v2/<capability>` | 二期能力预留契约，当前返回 501 |

聚合维度、指标和筛选字段均采用服务端白名单，查询值使用参数绑定。

## 测试

单元与 API 回归：

```powershell
python -m pytest -m "not integration" --cov=app
```

真实 SQL Server 集成测试：

```powershell
$env:RUN_DB_TESTS="1"
python -m pytest tests\test_integration_sqlserver.py -v
```

前端生产构建：

```powershell
Set-Location frontend
npm run build
```

## 一期与二期边界

一期已实现：全量数据接入、数据清洗、质量评估、SQL Server 存储、13 个分析维度、REST/SSE 服务、AI 问答、图表生成、报告生成、运营总览、数据资产和患者画像。

二期已预留：Redis 缓存、增量 MERGE、备份恢复、费用预测、再入院风险、Spark 分布式引擎、本地大模型、多轮会话、地图和更丰富的可视化。相关 feature flags、staging 表、存储接口及 `/api/v2/*` 契约已保留，但不会在一期误报为已上线。

本平台只处理脱敏聚合数据，AI 输出用于运营分析，不提供个人诊断或医疗建议。
