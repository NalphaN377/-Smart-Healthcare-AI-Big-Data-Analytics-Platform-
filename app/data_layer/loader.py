"""大数据批量读取：高效读取 CSV/TSV/JSON，分块读取避免内存溢出。

对应文档功能「大数据批量读取」：
- 兼容数十万条记录批量读取
- 优化读取效率，解决大文件读取卡顿、内存溢出问题
"""
import logging
from pathlib import Path

import pandas as pd

from config import CHUNK_SIZE

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".jsonl"}


def _detect_sep(filepath: Path) -> str:
    """根据扩展名推断分隔符：TSV 用制表符，其余默认逗号。"""
    return "\t" if filepath.suffix.lower() == ".tsv" else ","


def read_csv(filepath, chunk_size: int = CHUNK_SIZE, **kwargs):
    """分块读取 CSV/TSV，返回迭代器（TextFileReader）。

    分块读取的核心：`chunksize` 参数让 pandas 每次只读入 chunk_size 行，
    避免数十万条数据一次性载入内存导致卡顿 / OOM。

    Args:
        filepath: 文件路径。
        chunk_size: 每块行数。
        **kwargs: 透传给 pd.read_csv 的其余参数。
    """
    path = Path(filepath)
    sep = kwargs.pop("sep", _detect_sep(path))
    logger.info("开始分块读取 %s (chunk_size=%d, sep=%r)", path, chunk_size, sep)
    kwargs.setdefault("dtype", str)
    kwargs.setdefault("encoding", "utf-8-sig")
    kwargs.setdefault("on_bad_lines", "warn")
    return pd.read_csv(path, sep=sep, chunksize=chunk_size, low_memory=False, **kwargs)


def iter_chunks(filepath, chunk_size: int = CHUNK_SIZE, **kwargs):
    """统一迭代器：逐块产出 DataFrame，供清洗/入库逐块消费。

    用法：
        for chunk in iter_chunks("data/raw/hospital.csv"):
            cleaned = cleaner.clean(chunk)
            storage.bulk_insert(cleaned)
    """
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    if path.suffix.lower() in (".csv", ".tsv"):
        yield from read_csv(path, chunk_size=chunk_size, **kwargs)
    elif path.suffix.lower() in (".json", ".jsonl"):
        yield from _read_json_chunks(path, chunk_size=chunk_size, **kwargs)
    else:
        raise ValueError(f"不支持的文件格式: {path.suffix}")


def _read_json_chunks(filepath: Path, chunk_size: int = CHUNK_SIZE, **kwargs):
    """分块读取 JSON（按行 JSONL 格式，逐块读取避免一次性载入）。"""
    reader = pd.read_json(filepath, lines=True, chunksize=chunk_size, **kwargs)
    yield from reader


def read_all(filepath, **kwargs):
    """一次性读取（仅用于小文件调试或单元测试）。

    生产环境请优先使用 iter_chunks 分块读取。
    """
    path = Path(filepath)
    if path.suffix.lower() in (".csv", ".tsv"):
        sep = kwargs.pop("sep", _detect_sep(path))
        kwargs.setdefault("dtype", str)
        kwargs.setdefault("encoding", "utf-8-sig")
        return pd.read_csv(path, sep=sep, low_memory=False, **kwargs)
    if path.suffix.lower() in (".json", ".jsonl"):
        return pd.read_json(path, lines=True, **kwargs)
    raise ValueError(f"不支持的文件格式: {path.suffix}")
