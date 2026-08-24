# 报告插图：系统架构与数据流

本目录中的图基于当前代码实现绘制，技术口径为：SQL Server、Flask REST/SSE、规则意图识别、DeepSeek Anthropic 兼容 API、Vue 3 与 ECharts。Redis、Spark、预测模型、本地大模型等均以“二期预留”标注，未作为一期已上线能力。

## 图 1：系统架构图

- 推荐图题：`图 X-X 智慧医疗大数据与 AI 大模型分析平台系统架构`
- 推荐说明：系统采用分层架构。SPARCS 脱敏出院数据经批量接入、清洗、类型标准化、去重与质量评估后写入 SQL Server；Flask 服务通过白名单维度与指标完成参数化聚合查询；MedicalAgent 将自然语言意图映射为分析调用，并结合 DeepSeek 生成文字摘要，同时生成 ECharts 配置；Vue 3 前端以 REST 与 SSE 方式展示运营大屏、智能问答和洞察报告。
- 文件：`system_architecture.svg`（报告首选）、`system_architecture.png`、`system_architecture.pdf`、`system_architecture.dot`（可编辑源文件）。

## 图 2：数据流图

- 推荐图题：`图 X-X 智慧医疗大数据与 AI 大模型分析平台数据流图`
- 推荐说明：系统数据按照“原始数据—数据治理—SQL Server 存储—多维分析—AI 编排—可视化呈现”的顺序流转，最终形成运营大屏、动态图表和文字洞察。
- 文件：`data_flow.svg`（报告首选）、`data_flow.png`、`data_flow.pdf`、`data_flow.dot`（可编辑源文件）。

## 图例与报告口径

- 蓝色矩形：外部参与者或 Web/API 接口。
- 椭圆：数据处理过程。
- 圆柱体：数据存储。
- 实线箭头：一期已实现的数据/调用流。
- 虚线边框或箭头：二期预留能力或边界说明。
- 当前数据口径：原始 2,101,588 行，清洗去重后 2,094,418 行。

## 重新生成

安装 Graphviz 后，在本目录执行：

```powershell
dot -Tsvg system_architecture.dot -o system_architecture.svg
dot -Tpng -Gdpi=180 system_architecture.dot -o system_architecture.png
dot -Tpdf system_architecture.dot -o system_architecture.pdf
dot -Tsvg data_flow.dot -o data_flow.svg
dot -Tpng -Gdpi=180 data_flow.dot -o data_flow.png
dot -Tpdf data_flow.dot -o data_flow.pdf
```
