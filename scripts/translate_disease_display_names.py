"""从数据库读取疾病维度，并通过已配置的模型生成中文显示名 JSON。"""
from __future__ import annotations

import json
from pathlib import Path

from app.ai_layer.text_gen import _client
from app.data_layer.storage import get_connection
from config import LLM_CONFIG

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "config" / "disease_display_names.json"
DISPLAY_OVERRIDES = {
    "CORONAVIRUS DISEASE 2019 (COVID-19)": "新型冠状病毒感染",
    "COVID-19": "新型冠状病毒感染",
    "HIV INFECTION": "人类免疫缺陷病毒感染",
    "LEUKEMIA - ACUTE LYMPHOBLASTIC LEUKEMIA (ALL)": "急性淋巴细胞白血病",
    "LEUKEMIA - CHRONIC LYMPHOCYTIC LEUKEMIA (CLL)": "慢性淋巴细胞白血病",
    "LEUKEMIA - CHRONIC MYELOID LEUKEMIA (CML)": "慢性髓系白血病",
    "Leukemia - acute myeloid leukemia (AML)": "急性髓系白血病",
    "SEXUALLY TRANSMITTED INFECTIONS (EXCLUDING HIV AND HEPATITIS)": "性传播感染（不含人类免疫缺陷病毒感染和肝炎）",
}


def disease_names() -> list[str]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT ccsr_diagnosis_description "
            "FROM dbo.inpatient_discharge "
            "WHERE ccsr_diagnosis_description IS NOT NULL "
            "ORDER BY ccsr_diagnosis_description"
        )
        return [str(row[0]).strip() for row in cursor.fetchall() if str(row[0]).strip()]
    finally:
        conn.close()


def translate_batch(client, names: list[str]) -> dict[str, str]:
    prompt = (
        "把下面每个美国 CCSR 诊断分类名称翻译成简洁、准确的简体中文。"
        "返回一个严格 JSON 对象：键必须逐字保留输入英文，值只放中文疾病名称。"
        "不得省略、合并或增加条目；initial encounter 译为初次就诊，"
        "subsequent encounter 译为后续就诊，sequela 译为后遗症。\n"
        + json.dumps(names, ensure_ascii=False)
    )
    message = client.messages.create(
        model=LLM_CONFIG["model"], max_tokens=8000, temperature=0,
        system="你是医学术语本地化专家，只输出有效 JSON。",
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    translated = json.loads(text)
    missing = set(names) - set(translated)
    extra = set(translated) - set(names)
    if missing or extra:
        raise ValueError(f"翻译结果键不完整: missing={len(missing)}, extra={len(extra)}")
    return {name: str(translated[name]).strip() for name in names}


def main() -> None:
    names = disease_names()
    client = _client()
    result = {}
    for offset in range(0, len(names), 70):
        result.update(translate_batch(client, names[offset:offset + 70]))
    result.update({key: value for key, value in DISPLAY_OVERRIDES.items() if key in result})
    if len(result) != len(names) or any(not value for value in result.values()):
        raise ValueError("翻译结果数量不正确或包含空值")
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = OUTPUT_PATH.with_suffix(".json.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(f"已写入 {OUTPUT_PATH}：{len(result)} 项")


if __name__ == "__main__":
    main()
