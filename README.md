# 智慧医疗大数据与AI大模型分析平台

学生实训项目：基于美国纽约州 SPARCS 住院出院公开数据集，构建大数据分析与 AI 大模型分析平台。

## 目录结构

```
├── docs/                        # 交付文档
│   ├── 智慧医疗大数据与AI大模型分析平台.docx     # 项目主文档
│   ├── 智慧医疗大数据与AI大模型分析平台调研报告.docx  # 调研报告
│   └── docs_notes/             # 过程文档（例会纪要等）
├── templates/                   # 第1组完成的模板工件文档（0~15 号参考文档）
├── data/
│   └── raw/                     # 原始数据集（不入库，见 .gitignore）
│       └── Hospital_Inpatient_Discharges__...csv   # SPARCS 2021 住院数据（794MB）
└── .gitignore                   # git 忽略规则
```

## 开发环境

使用 Python 3.11，Conda 环境名 `healthcare`：

```bash
conda create -n healthcare python=3.11 -y
conda activate healthcare
pip install -r requirements.txt
```

新增依赖请指定版本并同步更新 `requirements.txt`。

## 注意事项

- `data/raw/` 下的原始数据集 **不提交到 git**（794MB 超 GitHub 100MB 单文件限制），已加入 `.gitignore`
- 模板文档为参考用，按实训要求在 `templates/` 中填写后，自行产生的交付文档放入 `docs/`
