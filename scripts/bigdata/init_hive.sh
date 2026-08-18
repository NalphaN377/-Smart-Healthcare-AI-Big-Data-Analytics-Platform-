#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

docker compose --profile bigdata exec -T namenode hdfs dfs -mkdir -p /medical/warehouse
docker compose --profile bigdata exec -T hiveserver2 \
  beeline -u 'jdbc:hive2://127.0.0.1:10000/default' \
  --silent=true -f /dev/stdin < docker/hive/init.sql
docker compose --profile bigdata exec -T hiveserver2 \
  beeline -u 'jdbc:hive2://127.0.0.1:10000/medical_analytics' \
  --silent=true -e 'SHOW CREATE TABLE hospital_discharges'
