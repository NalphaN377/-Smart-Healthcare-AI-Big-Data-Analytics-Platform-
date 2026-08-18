#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

LOCAL_FILE="data/processed/hospital_discharges_clean.parquet"
HDFS_DIR="/medical/processed/hospital_discharges"
HDFS_FILE="$HDFS_DIR/hospital_discharges_clean.parquet"

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Clean Parquet is missing: $LOCAL_FILE" >&2
  exit 1
fi

local_size="$(wc -c < "$LOCAL_FILE" | tr -d ' ')"
docker compose --profile bigdata exec -T namenode hdfs dfs -mkdir -p "$HDFS_DIR"

if docker compose --profile bigdata exec -T namenode hdfs dfs -test -e "$HDFS_FILE"; then
  hdfs_size="$(docker compose --profile bigdata exec -T namenode hdfs dfs -stat '%b' "$HDFS_FILE" | tr -d '\r')"
  if [[ "$hdfs_size" != "$local_size" ]]; then
    echo "HDFS target exists with a different size; refusing to overwrite: $HDFS_FILE" >&2
    exit 1
  fi
  echo "HDFS file already exists with matching size; upload skipped."
else
  existing_files="$(docker compose --profile bigdata exec -T namenode hdfs dfs -ls "$HDFS_DIR" 2>/dev/null | awk '$1 ~ /^-/ {count++} END {print count+0}')"
  if [[ "$existing_files" != "0" ]]; then
    echo "Unexpected file already exists in $HDFS_DIR; refusing to create another version." >&2
    exit 1
  fi
  docker compose --profile bigdata exec -T namenode hdfs dfs -put - "$HDFS_FILE" < "$LOCAL_FILE"
  echo "Uploaded the single official cleaned Parquet to HDFS."
fi

file_count="$(docker compose --profile bigdata exec -T namenode hdfs dfs -ls "$HDFS_DIR" | awk '$1 ~ /^-/ {count++} END {print count+0}')"
if [[ "$file_count" != "1" ]]; then
  echo "Expected exactly one HDFS data file, found $file_count" >&2
  exit 1
fi

docker compose --profile bigdata exec -T namenode hdfs dfs -cat "$HDFS_FILE" >/dev/null
docker compose --profile bigdata exec -T namenode hdfs dfs -ls -h "$HDFS_DIR"
docker compose --profile bigdata exec -T namenode hdfs dfs -du -h "$HDFS_DIR"
