#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -f data/processed/hospital_discharges_clean.parquet ]]; then
  echo "Clean Parquet is missing: data/processed/hospital_discharges_clean.parquet" >&2
  exit 1
fi

echo "Starting single-node HDFS and Hive without recreating MySQL..."
docker compose --profile bigdata up -d --wait --wait-timeout 360 \
  namenode datanode hive-metastore hiveserver2
docker compose --profile bigdata ps
