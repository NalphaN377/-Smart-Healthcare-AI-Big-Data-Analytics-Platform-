"""分块 ETL：原始住院数据 -> 清洗标准化 -> SQL Server。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.common.logger import get_logger  # noqa: E402
from app.data_layer import cleaner, loader, quality, storage  # noqa: E402
from config import CHUNK_SIZE, SOURCE_DATA_PATH  # noqa: E402

logger = get_logger("ingest")


def ingest(
    filepath: str | Path = SOURCE_DATA_PATH,
    *,
    chunk_size: int = CHUNK_SIZE,
    init_schema: bool = False,
    truncate: bool = False,
    dry_run: bool = False,
    max_chunks: int | None = None,
) -> dict:
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")

    if init_schema and not dry_run:
        storage.init_schema()
    if truncate and not dry_run:
        storage.truncate_table()

    run_id = None if dry_run else storage.start_ingestion(str(path), path.stat().st_size)
    started = time.perf_counter()
    totals = {"chunks": 0, "rows_read": 0, "rows_inserted": 0, "rows_dropped": 0}
    accumulator = quality.QualityAccumulator()

    try:
        for chunk in loader.iter_chunks(path, chunk_size=chunk_size):
            chunk = loader.normalize_source_columns(chunk)
            if totals["chunks"] == 0:
                cleaner.validate_columns(chunk, storage.COLUMN_MAPPING.keys())
            accumulator.update(chunk)
            cleaned, stats = cleaner.clean_with_stats(chunk)
            inserted = len(cleaned) if dry_run else storage.bulk_insert(cleaned)
            totals["chunks"] += 1
            totals["rows_read"] += stats["rows_read"]
            totals["rows_inserted"] += inserted
            totals["rows_dropped"] += stats["rows_read"] - len(cleaned)

            if run_id and (totals["chunks"] == 1 or totals["chunks"] % 5 == 0):
                storage.update_ingestion(
                    run_id, chunks=totals["chunks"], rows_read=totals["rows_read"],
                    rows_inserted=totals["rows_inserted"], rows_dropped=totals["rows_dropped"],
                )
            logger.info(
                "进度: %d 块 / 读取 %d / 写入 %d / 过滤 %d",
                totals["chunks"], totals["rows_read"], totals["rows_inserted"], totals["rows_dropped"],
            )
            if max_chunks and totals["chunks"] >= max_chunks:
                break

        report = quality_result = accumulator.result()
        totals.update({
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "quality": quality_result,
            "dry_run": dry_run,
            "source_file": str(path),
        })
        if run_id:
            storage.update_ingestion(
                run_id, chunks=totals["chunks"], rows_read=totals["rows_read"],
                rows_inserted=totals["rows_inserted"], rows_dropped=totals["rows_dropped"],
            )
            storage.finish_ingestion(run_id, status="completed", quality=report)
        return totals
    except Exception as exc:
        if run_id:
            storage.finish_ingestion(run_id, status="failed", error=str(exc))
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="智慧医疗大数据 SQL Server 分块 ETL")
    parser.add_argument("--file", default=str(SOURCE_DATA_PATH), help="CSV/TSV/JSON 数据文件")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--init-schema", action="store_true", help="执行幂等建表脚本")
    parser.add_argument("--truncate", action="store_true", help="入库前显式清空业务表")
    parser.add_argument("--dry-run", action="store_true", help="只清洗和评估，不连接数据库")
    parser.add_argument("--max-chunks", type=int, help="限制处理块数，仅用于联调")
    args = parser.parse_args()
    result = ingest(
        args.file, chunk_size=args.chunk_size, init_schema=args.init_schema,
        truncate=args.truncate, dry_run=args.dry_run, max_chunks=args.max_chunks,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
