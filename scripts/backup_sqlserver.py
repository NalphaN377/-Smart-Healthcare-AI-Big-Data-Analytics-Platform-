"""SQL Server备份、校验和隔离恢复命令行。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.data_layer import backup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="yiliaoBigData SQL Server备份恢复")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create", help="创建压缩全量COPY_ONLY备份并校验")
    create_parser.add_argument("--path", help="可选.bak路径，必须位于项目data/backup目录")
    list_parser = subparsers.add_parser("list", help="列出备份审计记录")
    list_parser.add_argument("--limit", type=int, default=20)
    verify_parser = subparsers.add_parser("verify", help="执行RESTORE VERIFYONLY")
    verify_parser.add_argument("--path", required=True)
    restore_parser = subparsers.add_parser("restore", help="恢复到新的隔离数据库，禁止覆盖业务库")
    restore_parser.add_argument("--path", required=True)
    restore_parser.add_argument("--target", required=True)
    restore_parser.add_argument("--confirm", required=True, help="格式 RESTORE:<target>")
    args = parser.parse_args()

    if args.command == "create":
        result = backup.create_full_backup(args.path)
    elif args.command == "list":
        result = backup.list_backups(args.limit)
    elif args.command == "verify":
        result = backup.verify_backup(args.path)
    else:
        result = backup.restore_to_new_database(args.path, args.target, args.confirm)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
