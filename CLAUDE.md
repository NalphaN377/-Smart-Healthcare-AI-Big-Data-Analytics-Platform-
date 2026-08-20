# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

软件工程实训项目（要求 CMMI3 / RUP / 敏捷过程规范 + Git 按功能提交）：**智慧医疗大数据与AI大模型分析平台**。

基于纽约州 SPARCS 2021 住院出院数据集（33 字段），实现「数据清洗 → SQL Server 入库 → 多维聚合 RESTful API → DeepSeek 自然语言交互 → Vue 3 + ECharts 可视化」的完整链路。**核心管理要点：大数据处理与分析是主线，AI 只是辅助交互入口**——写报告/答辩时不要把重点放反。

**当前状态：一期已完整实现并通过验收**（真实数据全量导入、15 项自动化测试、性能达标，详见 `README.md` 与 `TEST_REPORT.md`）。数据实际落库 **SQL Server 2019+**（非模板文档中写的 MySQL ），库名 `yiliaoBigData`；二期能力以 feature flags、staging 表、预留接口与 `/api/v2/*` 契约保留但不上线。

> ⚠️ **未提交的大规模重构**：工作区已把旧的 `backend/` 布局（`backend/app/{api,ai,models,...}`）重构为根级分层布局（`app/` + `config/` + `scripts/` + `sql/` + `tests/` + `frontend/`）。git 状态里 `backend/**` 全部为删除、新目录全部未跟踪（untracked）。**不要在 `backend/` 里新建或改文件**；若提交，一次性把整个重构作为一次提交。重构完成后请更新 README 的目录清单。

## 必读文档（动手前先读）

- `docs/docs_notes/项目解析.md` — 项目权威档案：三大模块（一期必做 + 二期加分）、技术架构、33 字段数据集分组、已知"坑"、推荐实施路线。写报告前先通读。**注意**：文中"MySQL"已落地为 SQL Server，"大数据/Spark"以单机 Pandas 为主、预留接口。
- `docs/docs_notes/团队分工协作规范.md`、`docs/docs_notes/3.项目开发计划.md` — 5 人分工、接口契约、Git 约定、里程碑与计划。
- `docs/` 下的交付成品：`0.调研报告.docx`、`1.配置管理计划书.docx`、`2.软件需求规约.docx`、`3.项目进度计划.xlsx` 及若干中途分析报告 `.md`。
- `templates/`（未入 git，参考样板）——改文档优先落 `docs/docs_notes/`。

## 目录结构与架构

| 路径 | 说明 |
|---|---|
| `app/data_layer/` | 数据链路：`loader.py`（pandas 分块读取）、`cleaner.py`（清洗去重）、`quality.py`（质量四维评分）、`storage.py`（SQL Server 连接/建表/BULK 入库/导入审计） |
| `app/service_layer/` | 服务与 API：`analysis/aggregation.py`（白名单多维聚合）、`api/routes.py`（`/api` 蓝图 + SSE）、`app.py`（Flask 应用工厂） |
| `app/ai_layer/` | `intent.py`（规则关键词意图识别，二期可切 LLM）、`agent.py`（意图→取数→摘要+图表的编排）、`text_gen.py` / `chart_gen.py` / `report.py` |
| `app/common/` | `response.py`（统一 `{code,message,data,meta}` 响应 + `timing()` 耗时装饰器）、`logger.py` |
| `config/settings.py` | 全部配置只从环境变量 / 项目根 `.env` 读取，含 DB、LLM、Flask 与二期 feature flags |
| `sql/schema.sql` | SQL Server 2019+ Schema：`inpatient_discharge_stage`（staging）、业务表、`ingestion_run` 审计表、二期预留表 |
| `scripts/` | `ingest.py`（通用 Pandas 分块导入）、`bulk_ingest_sqlserver.py`（BULK INSERT + SQL 清洗高速全量导入） |
| `tests/` | 单元 + API 契约（monkeypatch 掉 DB/LLM）+ 真实 SQL Server 集成测试 |
| `frontend/` | Vue 3 + Vite + ECharts 单页大屏：`App.vue` + `ChatPanel.vue` / `ChartPanel.vue` / `DashboardChart.vue`，`api/client.js` |

架构要点（跨文件才能看懂）：

- **分层单向依赖**：`ai_layer → service_layer → data_layer`；Agent 默认**同进程直调**聚合函数取数（`agent._fetch_data`），而非走 HTTP，改走 HTTP 只动这一处。
- **所有动态 SQL 走白名单 + 参数绑定**：`aggregation.DIMENSIONS / METRICS / FILTERS` 三个白名单 dict 把用户输入映射到列名与表达式，用户值只能作参数传入，杜绝 SQL 注入。新增维度/指标 = 改这三个 dict。
- **CSV 列名映射保存在 `storage.COLUMN_MAPPING`**（驼峰/带空格原始名 → snake_case 列名），`dataframe_records()` 据此校验并转行记录；字段顺序即入库列顺序。
- **统一 JSON 响应**：`{"code":0,"message","data","meta":{"elapsed_ms":...}}`；`timing()` 装饰器自动把 `ValueError`→400、其他异常→500。
- **一期/二期边界**：`config.FEATURES`（`llm_intent`/`redis_cache`/`ml_analysis`/`local_llm`/`distributed_engine`）默认关；`storage.incremental_update()/backup()/restore()` 抛 `NotImplementedError`；`/api/v2/<capability>` 返回 501。二期实现时补这些占位即可，不破坏现有契约。

## 常用命令

环境：Python **3.11**（`.python-version`=3.11.9）。用项目内自带解释器：`.\.venv311\Scripts\python.exe`（已建好 venv）；本机 `py -3.11` 也可。安装依赖 `pip install -r requirements.txt`（Flask、pandas、pymssql、anthropic、pytest）。

```powershell
# 启动后端（监听 127.0.0.1:5000，端口/密钥在 .env 配置）
.\.venv311\Scripts\python.exe run.py

# 单元 + API 回归（不连数据库；monkeypatch 掉 storage/LLM）
.\.venv311\Scripts\python.exe -m pytest -m "not integration" --cov=app

# 真实 SQL Server 集成测试（需已建库 yiliaoBigData 并完成导入）
$env:RUN_DB_TESTS="1"
.\.venv311\Scripts\python.exe -m pytest tests\test_integration_sqlserver.py -v

# 前端（终端二）
Set-Location frontend
npm install      # 首次
npm run dev      # http://127.0.0.1:5173，/api 代理到 5000
npm run build    # 生产构建
```

数据导入（目标库 `yiliaoBigData` 需先创建）——高速 BULK 全量导入（`--truncate` 会清空业务表，仅主动全量重导时用）：

```powershell
.\.venv311\Scripts\python.exe scripts\bulk_ingest_sqlserver.py --file "<CSV路径>" --truncate
.\.venv311\Scripts\python.exe scripts\ingest.py --file "<CSV路径>" --init-schema   # Pandas 标准链路
```

当前工作区已完成全量导入：原始 2,101,588 行 → 清洗去重后 2,094,418 行（质量评分 99.98%）。原始 CSV（800MB）在 `data/raw/` 或 `SOURCE_DATA_PATH` 指向的路径。

完整接口表与一期/二期边界见 `README.md`（核心：`/api/overview`、`/api/aggregate`、`/api/avg_length_of_stay`、`/api/cost_distribution`、`/api/payment_ratio`、`/api/year_trend`、`/api/data-quality`、`POST /api/chat`、`POST /api/chat/stream`、`POST /api/reports`、`/api/health`）。

## 关键约定

- `.env`（含 DB 密码与 `DEEPSEEK_API_KEY`）被 gitignore，**绝不提交**；改配置默认值走 `.env.example`。
- LLM 为 DeepSeek 的 Anthropic 兼容端点：`ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic`，模型 `deepseek-v4-flash`，SDK 用 `anthropic`；未配 key 时 AI 端点有模板兜底，测试不受影响。
- 导入审计：每次导入写 `dbo.ingestion_run`，`/api/data-quality` 返回最近一次的四维质量报告。
- 前端 ECharts 按需引入并分包（`vite.config.js` 中 `manualChunks`），改图表组件时保持该拆分。

## 报告写作必须规避的已知坑（源自《项目解析》§七，写文档时核对）

- **爬虫需求是模板残留**：技术表里"Scrapy 采集就业信息"来自就业模板，与本项目无关，删掉或弱化；数据是本地提供的 CSV。
- **数据量口径**：已实测 210 万行（原文案"数十万条"是模板口径）。报告统一写明实测数据，体现"本地全量 210 万行 + 理论支撑更大"。
- **图表/章节编号混乱**：模板有"图7-1/表7-1"断章和"（1）vs 1）"混排，交付前理顺编号。
- **大数据 vs 实际体量**：文档要求 Hadoop/Spark/Hive 全套，实际为单机 Pandas + SQL Server → 写报告时强调"单机为主、预留 Spark/Hive 接口"的两期策略。
- **MySQL vs SQL Server**：模板/项目解析写 MySQL，实现与验收均为 SQL Server，报告要统一。
- **LLM 部署**：一期云端 DeepSeek API，二期可选 Qwen/BaiChuan + 本地化。

## Git 约定

- 开发分支 `feature/data`、`feature/api`、`feature/ai`、`feature/frontend`、`feature/docs`；`main`/`master` 只放稳定版本。
- 提交格式 `feat(data): ...` / `fix(api): ...` / `docs: ...`，每完成一个功能提交一次（CMMI 按功能提交要求），禁止强推主干。
- 提交信息用中文，并附 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- **待办**：当前 `backend/ → app/+config/` 的大重构尚未提交（详见上文警告），涉及大量删除 + 新增。