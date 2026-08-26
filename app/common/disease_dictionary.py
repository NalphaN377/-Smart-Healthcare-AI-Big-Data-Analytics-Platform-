"""疾病中英文别名到 SPARCS CCSR 疾病描述的受控映射。"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from config import BASE_DIR

DICTIONARY_PATH = BASE_DIR / "config" / "disease_dictionary.json"
DISPLAY_NAMES_PATH = BASE_DIR / "config" / "disease_display_names.json"


@lru_cache(maxsize=1)
def entries() -> tuple[dict, ...]:
    raw = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("疾病词典必须是数组")
    clean = []
    for item in raw:
        canonical = str(item.get("canonical") or "").strip().upper()
        chinese = str(item.get("chinese") or "").strip()
        english = str(item.get("english") or canonical).strip()
        aliases = {canonical, english, chinese, *(str(value).strip() for value in item.get("aliases") or [])}
        aliases.discard("")
        if not canonical or not chinese or not aliases:
            raise ValueError("疾病词典条目缺少 canonical、chinese 或 aliases")
        clean.append({
            "code": str(item.get("code") or "").strip(), "canonical": canonical,
            "english": english, "chinese": chinese,
            "aliases": tuple(sorted(aliases, key=len, reverse=True)),
        })
    return tuple(clean)


def resolve(text: str) -> dict | None:
    """在自然语言中按最长别名优先匹配疾病，返回一份安全副本。"""
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = value.casefold()
    candidates = []
    for item in entries():
        for alias in item["aliases"]:
            position = lowered.find(alias.casefold())
            if position >= 0:
                candidates.append((len(alias), -position, item, alias))
    if not candidates:
        return None
    _length, _position, item, alias = max(candidates, key=lambda value: (value[0], value[1]))
    return {key: value for key, value in item.items() if key != "aliases"} | {"matched_alias": alias}


def normalize(value: str) -> str:
    matched = resolve(value)
    return matched["canonical"] if matched else str(value or "").strip()


@lru_cache(maxsize=1)
def display_names() -> dict[str, str]:
    raw = json.loads(DISPLAY_NAMES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("疾病显示词典必须是对象")
    return {str(key).strip().upper(): str(value).strip() for key, value in raw.items() if str(key).strip() and str(value).strip()}


def bilingual_label(value: str) -> str:
    canonical = str(value or "").strip().upper()
    for item in entries():
        if item["canonical"] == canonical:
            return f"{item['chinese']}（{item['english']}）"
    return str(value or "")


def chinese_label(value: str) -> str:
    """返回中文展示名；词典未收录时保留原值。"""
    normalized = str(value or "").strip()
    for item in entries():
        if any(normalized.casefold() == alias.casefold() for alias in item["aliases"]):
            return item["chinese"]
    return display_names().get(normalized.upper(), normalized)
