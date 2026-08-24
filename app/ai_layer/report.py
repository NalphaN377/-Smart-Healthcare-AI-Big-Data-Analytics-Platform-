"""医疗洞察报告生成：基于多轮/深度分析结果生成简要洞察报告。

对应文档功能「医疗洞察报告生成」：突出大数据挖掘价值。
"""
import logging
from concurrent.futures import ThreadPoolExecutor

from app.ai_layer.text_gen import generate_summary

logger = logging.getLogger(__name__)


def generate_report(results: list, title: str = "医疗大数据洞察报告") -> str:
    """将多个分析结果汇总为 Markdown 洞察报告。

    Args:
        results: 分析结果字典列表，如
            [{"title": "年龄段分布", "data": {...}}, ...]
        title: 报告标题。

    Returns:
        Markdown 格式报告文本。
    """
    with ThreadPoolExecutor(max_workers=min(4, len(results))) as executor:
        summaries = list(executor.map(lambda item: generate_summary(item.get("data", {}), f"请概括报告章节：{item.get('title', '分析')}"), results))

    lines = [f"# {title}", ""]
    for item, summary in zip(results, summaries):
        section_title = item.get("title", "分析")
        lines.append(f"## {section_title}")
        lines.append("")
        lines.append(summary)
        lines.append("")
    report_text = "\n".join(lines)
    logger.info("生成洞察报告: %s（%d 个章节）", title, len(results))
    return report_text
