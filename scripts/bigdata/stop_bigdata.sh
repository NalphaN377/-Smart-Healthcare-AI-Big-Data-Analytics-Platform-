#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

docker compose --profile bigdata stop hiveserver2 hive-metastore datanode namenode
echo "Big-data services stopped. Named volumes and the MySQL service were preserved."
