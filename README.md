# 智慧医疗大数据与 AI 大模型分析平台

基于 2021—2024 年 SPARCS 脱敏住院出院数据建设的智慧医疗分析平台，覆盖 33 字段数据治理、SQL Server 持久化、多维与关联分析、费用预测、持久化 AI 对话、洞察报告和 Vue 3 可视化大屏。

当前工作区已完成四年数据导入，去重后共 8,508,252 条记录；其中 2021 年 2,094,418 条、2022 年 2,099,523 条、2023 年 2,121,712 条、2024 年 2,192,599 条。

## 技术架构

                 ┌─────────────────────────┐
                 │       用户访问层         │
                 │ 患者 / 医生 / 系统管理员 │
                 └────────────┬────────────┘
                              │
                 ┌────────────▼────────────┐
                 │       前端展示层         │
                 │ Vue 3 / ECharts / Vite  │
                 │ 看板、AI问答、报告、管理 │
                 └────────────┬────────────┘
                              │ REST / SSE
                 ┌────────────▼────────────┐
                 │       服务接口层         │
                 │         Flask           │
                 │ API、权限、Session、审计 │
                 └───────┬─────────┬───────┘
                         │         │
        ┌────────────────▼──┐   ┌──▼────────────────┐
        │   数据分析与AI层   │   │    业务服务层      │
        │ 聚合分析 / RAG     │   │ 用户/报告/通知/对话│
        │ DeepSeek / ML模型  │   │ 备份/质量/缓存管理 │
        └─────────┬─────────┘   └─────────┬─────────┘
                  │                       │
        ┌─────────▼───────────────────────▼─────────┐
        │               数据与基础设施层             │
        │ SQL Server / Redis / 模型文件 / 原始CSV   │
        └───────────────────────────────────────────┘

```text
SPARCS CSV
  → Pandas / SQL Server BULK INSERT 清洗与校验
  → SQL Server（业务表、索引、导入审计）
  → SQL Server 关联预聚合 + scikit-learn 费用模型
  → Flask REST / SSE 分析服务 + SQL Server 持久化对话
  → DeepSeek 结构化语义识别 + SQL精确聚合 + 轻量混合RAG + 本地规则兜底
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
scripts/refresh_associations.py   诊断—手术关联统计全量重建
scripts/refresh_dashboard_stats.py 运营总览轻量预汇总重建
scripts/train_cost_model.py       费用预测模型训练与激活
sql/schema.sql                    SQL Server 表、索引和二期 staging 表
tests/                            单元、API 与真实数据库集成测试
```

## 本地运行

### 1. 后端环境

项目统一使用 Python 3.11（当前验证版本为 3.11.9）。

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

当前工作区已提供项目内 Python 3.11.9；如本机未注册 `py -3.11`，可直接使用：

```powershell
.\.python311\python.exe -m venv .venv311
```

编辑 `.env`，至少填写：

```dotenv
DB_HOST=localhost
DB_PORT=1433
DB_USER=sa
DB_PASSWORD=你的本机密码
DB_NAME=yiliaoBigData
DEEPSEEK_API_KEY=你的密钥
FEATURE_LLM_INTENT=true
SECRET_KEY=至少32位的随机字符串
```

密钥与密码只放在已被 Git 忽略的 `.env` 或 PyCharm 运行环境变量中，不要提交到仓库。

### 2. 初始化数据库与管理员

已有数据库也需要重新执行幂等 Schema 初始化，以创建用户、审计和报告表：

```powershell
.\.venv311\Scripts\python.exe -c "from app.data_layer.storage import init_schema; init_schema()"
.\.venv311\Scripts\python.exe scripts\create_admin.py --username admin
```

管理员首次登录后必须修改初始密码。密码至少 10 位并同时包含字母和数字。

### 3. 数据库与全量导入

创建空数据库 `yiliaoBigData` 后，可执行高速导入。脚本会初始化 Schema、BULK INSERT 到 staging 表、清洗转换、去重并记录质量审计。

```powershell
.\.venv311\Scripts\python.exe scripts\bulk_ingest_sqlserver.py `
  --file "..\data\Hospital_Inpatient_Discharges__SPARCS_De-Identified___2021_20231012.csv" `
  --truncate
```

小文件或非 SQL Server 原生导入场景也可使用：

```powershell
.\.venv311\Scripts\python.exe scripts\ingest.py --file "..\data\your_file.csv" --init-schema
```

`--truncate` 会清空业务表，仅在明确需要重新全量导入时使用。

### 3.1 二期多年度增量导入

增量导入不会清空业务表。脚本会校验33字段契约、兼容2024年的字段改名，使用文件SHA-256防止同一文件重复处理，并通过暂存表和标准化行哈希实现幂等追加。

先做不连接数据库的字段检查：

```powershell
.\.venv311\Scripts\python.exe scripts\incremental_ingest_sqlserver.py `
  --directory "..\data" --validate-only
```

SQL Server启动且Schema初始化后，导入data目录下2022—2024文件：

```powershell
.\.venv311\Scripts\python.exe scripts\incremental_ingest_sqlserver.py `
  --directory "..\data"
```

每个文件独立记录导入批次、文件指纹、读取/新增/跳过行数和质量评分。成功批次会提升`data_version`，Redis查询缓存随新版本自动失效。若同一文件曾成功处理，脚本直接跳过；需要重新核对时可增加`--force`，但行哈希仍会阻止重复数据入库。

### 3.2 Redis查询缓存

Redis使用数字数据库编号，不使用数据库名称。本项目默认连接`127.0.0.1:6379/0`，并用`yiliaoBigData:`键前缀隔离：

```dotenv
FEATURE_REDIS_CACHE=true
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
REDIS_KEY_PREFIX=yiliaoBigData
REDIS_DEFAULT_TTL=300
```

缓存键包含用户角色、查询参数和数据版本，避免跨权限复用及增量入库后的旧结果残留。Redis不可用时服务自动降级为直接查询SQL Server。

### 3.3 SQL Server备份与恢复

创建压缩全量`COPY_ONLY`备份，并自动执行校验：

```powershell
.\.venv311\Scripts\python.exe scripts\backup_sqlserver.py create
```

列出审计记录或重新校验指定文件：

```powershell
.\.venv311\Scripts\python.exe scripts\backup_sqlserver.py list
.\.venv311\Scripts\python.exe scripts\backup_sqlserver.py verify --path "data\backup\your-backup.bak"
```

恢复工具禁止覆盖业务数据库，只允许恢复到新的隔离数据库，并要求显式确认：

```powershell
.\.venv311\Scripts\python.exe scripts\backup_sqlserver.py restore `
  --path "data\backup\your-backup.bak" `
  --target "yiliaoBigData_restore_check" `
  --confirm "RESTORE:yiliaoBigData_restore_check"
```

备份和恢复使用独立的无限命令超时执行通道；普通Web查询仍保持`DB_QUERY_TIMEOUT`限制。

### 3.4 关联分析与费用预测

首次部署或需要修复统计时，重建主要诊断—主要手术预聚合表：

```powershell
.\.venv311\Scripts\python.exe scripts\refresh_associations.py
```

后续增量导入会在同一事务内自动合并本批次统计。在线接口从预聚合表计算支持度、置信度和提升度，避免扫描850万条业务数据。该分析是“出院记录级主要诊断—主要手术组合”，不代表患者级疾病共现或因果关系。

运营总览同样使用轻量预汇总，首次部署或需要修复时执行：

```powershell
.\.venv311\Scripts\python.exe scripts\refresh_dashboard_stats.py
```

预汇总按服务区域保存总量、设施集合和六类常用维度统计。后续增量导入会在预汇总水位有效时自动合并本批次；若统计版本落后于业务数据版本，接口会拒绝使用旧汇总并回退到业务表查询。
当前工作区全量冷查询总览实测约0.20秒，替代了超过60秒的多次全表扫描。

训练并激活费用预测模型：

```powershell
.\.venv311\Scripts\python.exe scripts\train_cost_model.py --sample-per-year 50000
```

训练成功后设置`FEATURE_ML_ANALYSIS=true`并重启后端。

模型使用2021—2023年训练、2024年时间外验证，且不使用`Total Charges`作为特征。当前激活基线模型的2024年测试指标为：MAE 8,775.35美元、中位绝对误差3,229.60美元、RMSE 27,959.76美元、R² 0.6155。它用于已编码住院信息的最终成本运营估算，不是入院前预测、结算依据或医疗建议。

### 4. 启动后端和前端

终端一：

```powershell
.\.venv311\Scripts\python.exe run.py
```

终端二：

```powershell
Set-Location frontend
npm install
npm run dev

Set-Location D:\hwadee_project_workspace\smart_healthcare_platform\frontend
npm run dev -- --host 0.0.0.0 --strictPort
```

访问 `http://127.0.0.1:5173`。Vite 会将 `/api` 代理到 `http://127.0.0.1:5000`。

运营总览除基础住院量、住院日、费用和机构覆盖外，还会按当前角色加载年度同比 KPI、疾病负担四象限、服务区域年度热力图和疾病住院量变化榜。趋势年份、疾病气泡、区域热力单元格和疾病排名均支持点击下钻，当前分析条件以可清除的筛选标签显示；双对象比较支持年份、区域或两家医院之间的比较。医院比较对患者开放住院记录、住院日、名义账单、疾病构成和年度趋势；医生增加实际成本、急诊/手术/长住院占比和病例结构，管理员进一步显示病例组合校正指数。变化榜可切换增长最快、下降最多和绝对变化，并可把当前筛选及比较条件一键带入 AI 解读。医院差异仅用于运营分析，不代表医疗质量评级；增强分析独立容错，不会因单项专题暂时不可用而阻断基础总览。

### 4.1 前端费用预测

患者、医生和管理员登录后，均可从左侧工作台进入“费用预测”：

1. 填写服务区域、年龄段、入院类型和住院日等基本信息。
2. 尽可能补充CCSR诊断/手术编码、APR分组和严重程度；可选字段留空时由模型按缺失值规则处理。
3. 点击“开始预测”，右侧展示美元计价的预测总成本、基于时间外测试MAE的近似误差范围，以及模型版本和验证指标。
4. 点击“重置”可清空本轮结果并恢复示例值。

该页面使用专用权限`cost_prediction:use`，三类角色均拥有此权限。后端仍强制校验登录Session、CSRF Token、特征白名单和数值范围。预测仅用于已编码住院信息的运营成本估算，不是患者结算、保险理赔、入院前承诺或医疗建议。

## 核心接口

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/auth/login` | 登录并建立安全 Session |
| GET | `/api/auth/captcha` | 获取一次性登录图形验证码 |
| POST | `/api/auth/register` | 患者或医生自助注册 |
| GET | `/api/auth/me` | 当前用户、角色与权限 |
| DELETE | `/api/auth/account` | 患者或医生验证密码后注销账号 |
| GET | `/api/health` | 不暴露内部信息的公共健康检查 |
| GET | `/api/overview` | 前端运营总览聚合数据 |
| GET | `/api/aggregate` | 白名单维度/指标通用聚合 |
| GET | `/api/avg_length_of_stay` | 平均住院日分析 |
| GET | `/api/cost_distribution` | 费用和成本分析 |
| GET | `/api/payment_ratio` | 支付方式占比 |
| GET | `/api/year_trend` | 年度趋势 |
| GET | `/api/data-quality` | 最近导入与四维质量报告 |
| POST | `/api/chat` | AI 非流式完整分析 |
| POST | `/api/chat/stream` | AI SSE 流式分析 |
| GET | `/api/conversations` | 当前用户的持久化对话列表 |
| GET/DELETE | `/api/conversations/<id>` | 查看或归档自己的对话 |
| GET | `/api/v2/analytics/catalog` | 返回当前角色可用的维度、指标、单位与口径 |
| POST | `/api/v2/analytics/query` | 角色感知的一至二维通用聚合查询 |
| POST | `/api/v2/analytics/topics/<topic>` | 四年趋势与专项数据挖掘入口 |
| GET | `/api/v2/analytics/hospitals` | 当前服务区域的医疗机构目录（比较时校验样本阈值） |
| POST | `/api/v2/analytics/hospital-compare` | 患者、医生和管理员的角色感知双医院比较 |
| GET | `/api/v2/associations/disease-procedure` | 主要诊断—主要手术关联分析 |
| POST | `/api/v2/predictions/cost` | 已编码住院信息的总成本估算 |
| POST | `/api/v2/readmission-risk` | 返回再入院模型所缺的数据契约（422） |
| POST | `/api/reports` | Markdown 洞察报告 |
| GET | `/api/reports/public` | 登录用户查看已发布公开报告 |
| PUT | `/api/admin/reports/<id>/withdraw` | 管理员撤回已发布报告并同步删除接收者通知 |
| GET | `/api/notifications` | 当前用户的通知列表与未读数 |
| PUT | `/api/notifications/<id>/read` | 将自己的一条通知标为已读 |
| PUT | `/api/notifications/read-all` | 将当前用户的全部通知标为已读 |
| GET/POST | `/api/admin/users` | 管理员用户管理 |
| DELETE | `/api/admin/users/<id>` | 管理员删除其他账号 |
| GET | `/api/admin/system/health` | 管理员查看详细服务状态 |
| GET | `/api/admin/audit-logs` | 管理员查看安全审计 |
| GET/POST | `/api/v2/<capability>` | 尚未启用的二期能力统一返回明确的 501 契约 |

聚合维度、指标和筛选字段均采用服务端白名单，查询值使用参数绑定。

### 四年数据挖掘与权限

跨年清洗和查询层会同时统一年龄段与服务区域别名，预汇总也按统一后的标签分组。指标注册表是维度表达式、指标公式、显示单位、最小样本量、适用角色和限制说明的唯一事实源；前端或大模型传入的字段名不能绕过注册表。

专题接口与 AI 工具路由已覆盖：疾病四年趋势、病例复杂度与资源效率、病例组合校正医院比较、诊断—手术路径、急诊与入院路径、出院结局与风险分层、支付方式、人口与健康差异、妇产与新生儿、医院与区域运营、医院集中度，以及数据质量和异常检测。通用趋势支持“年份 × 业务维度”的二维结果及同比字段，图表按序列展示，并只保留住院量最高的前 8 条曲线以控制可读性。

角色边界由后端执行：

- 患者仅能查询疾病、年份、服务区域以及公开的住院量、平均住院日和次均账单费用；分组少于 11 条的结果被抑制。
- 医生可以使用临床、路径、结局、支付和人口专题；性别、种族、族裔、邮编和出生体重等敏感分组至少 30 条才展示。
- 管理员额外拥有财务代理指标、病例组合医院基准、医院集中度和数据质量专题。收费—成本差额率不是利润率，因为数据不含实际净收入、合同折扣、坏账、补贴和期间费用。

管理员常用专题名为 `hospital_benchmark`、`regional_concentration`、`data_quality`；其他专题名为 `growth_ranking`、`disease_trend`、`complexity`、`pathway`、`emergency`、`outcome`、`payment`、`demographic`、`maternal_newborn`、`operations`。增长排名同时返回首末年度值、增长率、绝对增长量、逐年值和样本量，每个年度至少100条记录才参与排名。

AI 问答会先判断问题是否属于当前脱敏住院数据范围，再解析维度、指标、筛选、排序和图表类型。只有意图明确且查询到有效数据时才生成图表；信息不足时会请用户补充，越界问题和个人诊疗问题不会触发数据库聚合或图表生成。DeepSeek 不可用时自动回退到本地同义词与语义规则。

### 混合RAG问答

AI问答采用“结构化查询 + 检索增强生成”，两类信息分开处理：

- 年度人次、平均住院日、费用等会变动数字始终通过白名单参数化SQL聚合实时计算，并支持`year_from`/`year_to`范围。用户问题中显式年份范围会覆盖外部模型的单年误判。
- 指标口径、CCSR/APR解释、数据范围、预测边界和安全规则从`docs/ai_knowledge.json`检索；当前数据版本、年度覆盖、模型登记和导入质量则按需从SQL元数据生成，不复制成会过期的静态数字。
- 检索使用关键词与中英文字符片段混合评分，当前规模无需额外向量数据库。每次最多注入3条、每条最多700字；对话历史仅保留最近6条且每条截断为300字，用于控制上下文体积。
- 知识文档在检索前按`patient`/`doctor`/`admin`角色过滤。个人诊断、处方和用药问题仍由安全路由直接拒绝，RAG不能绕过该边界。

例如“2021到2024年出院人数趋势”会查询SQL并返回四个年度的精确聚合；“出院人数的统计口径是什么”则从知识库回答，说明它实际是出院记录人次而非去重自然人数。

平台使用 HttpOnly、SameSite Session Cookie 和 CSRF Token。患者、医生、运维员的权限由后端强制检查；侧边栏和路由守卫只用于改善界面体验。患者总览不会返回年龄、性别、支付方式和严重程度画像，患者 AI 也只能调用公开疾病、年份和服务区域聚合工具。

费用预测是三类账户共享的独立能力，不会因此向患者开放患者画像、数据资产或管理接口。

登录页提供患者和医生自助注册入口。公开注册接口只接受 `patient`、`doctor`，不能创建 `admin`；忘记密码仍由管理员在用户管理页面重置。

患者和医生可在“账户设置”中验证当前密码并注销自己的账号。管理员可在用户管理页面删除除自己之外的账号。两种操作均使用软删除：账号立即无法登录并从用户列表隐藏，但历史报告和安全审计继续保留。

从分析报告卡片生成报告时，系统会保留该卡片的标题和对应分析章节，避免不同报告被统一命名。管理员首次发布分析报告时，系统会在同一数据库事务中为所有活跃患者和医生创建幂等通知。工作台铃铛每30秒轮询未读数；有未读消息时显示红点。通知列表支持单条已读和全部已读，点击报告通知会打开公开报告页并选中对应报告。管理员可在公开报告页撤回已发布报告；报告状态回退为草稿，并在同一事务中删除患者和医生收到的对应通知。公开报告页和通知页每30秒同步一次，手动刷新可立即看到变化。所有通知查询和已读操作均在后端按当前`user_id`隔离。

## 测试

单元与 API 回归：

```powershell
.\.venv311\Scripts\python.exe -m pytest -m "not integration" --cov=app
```

真实 SQL Server 集成测试：

```powershell
$env:RUN_DB_TESTS="1"
.\.venv311\Scripts\python.exe -m pytest tests\test_integration_sqlserver.py -v
```

前端生产构建：

```powershell
Set-Location frontend
npm run build
```

## 一期与二期边界

一期已实现：全量数据接入、数据清洗、质量评估、SQL Server 存储、29 个注册分析维度、REST/SSE 服务、AI 问答、图表生成、报告生成、运营总览、数据资产和患者画像。

二期已实现：统一异常追踪号、数据版本、Redis查询缓存、字段漂移兼容、文件指纹和行哈希幂等增量导入、SQL Server压缩备份/校验/隔离恢复、诊断—手术预聚合关联分析、费用预测模型登记与推理、持久化多轮对话，以及图表缩放、数据视图、还原、图片导出和点击事件。

二期后续：取得患者纵向标识与30天结局标签后训练再入院风险模型；取得可靠的医疗机构经纬度主数据后建设地图；在数据规模或关联算法需要跨节点计算时引入Spark；LLM本地化部署按本阶段约定不实施。当前850万条数据的导入、预聚合和基线机器学习均由SQL Server/Pandas/scikit-learn稳定完成，因此尚未为了形式引入Spark。

本平台只处理脱敏聚合数据，AI 输出用于运营分析，不提供个人诊断或医疗建议。
