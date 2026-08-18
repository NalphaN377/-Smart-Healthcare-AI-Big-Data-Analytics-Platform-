#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

EXPECTED_ROWS=2094483
EXPECTED_FACILITIES=205
HDFS_URI="hdfs://namenode:8020/medical/processed/hospital_discharges"

echo "Verifying HDFS health and the single official Parquet..."
docker compose --profile bigdata exec -T namenode hdfs dfsadmin -report
docker compose --profile bigdata exec -T namenode hdfs dfs -ls -h /medical/processed/hospital_discharges

echo "Verifying Hive counts..."
hive_output="$(
  docker compose --profile bigdata exec -T hiveserver2 \
    beeline -u 'jdbc:hive2://127.0.0.1:10000/medical_analytics' \
    --silent=true --showHeader=false --outputformat=tsv2 \
    -e "SELECT CONCAT(CAST(COUNT(*) AS STRING), ':', CAST(COUNT(DISTINCT CASE WHEN facility_name IS NOT NULL AND TRIM(facility_name) <> '' THEN TRIM(facility_name) END) AS STRING)) FROM hospital_discharges"
)"
hive_pair="$(printf '%s\n' "$hive_output" | grep -E '^[0-9]+:[0-9]+$' | tail -n 1)"
if [[ "$hive_pair" != "$EXPECTED_ROWS:$EXPECTED_FACILITIES" ]]; then
  echo "Hive consistency failed: expected $EXPECTED_ROWS:$EXPECTED_FACILITIES, got ${hive_pair:-no result}" >&2
  exit 1
fi
echo "Hive record_count: $EXPECTED_ROWS"
echo "Hive facility_count: $EXPECTED_FACILITIES"

docker compose --profile bigdata exec -T hiveserver2 \
  beeline -u 'jdbc:hive2://127.0.0.1:10000/medical_analytics' \
  --silent=true -f /dev/stdin < docker/hive/verify.sql

echo "Running the existing eight-analysis Spark job from HDFS in local[*] mode..."
spark_output="$(
  docker compose --profile tools run --rm --no-deps spark-client \
    /opt/spark/bin/spark-submit --master 'local[*]' \
    --conf spark.hadoop.fs.defaultFS=hdfs://namenode:8020 \
    --conf spark.sql.shuffle.partitions=8 \
    /opt/medical/jobs/medical_analytics.py \
    --source hdfs --hdfs-uri "$HDFS_URI" \
    --output /tmp/hdfs_medical_analytics.json --limit 10 2>&1
)"
printf '%s\n' "$spark_output"
grep -q "Spark records analyzed: 2,094,483" <<<"$spark_output"
grep -q "Spark facility count: 205" <<<"$spark_output"
grep -q "Spark analyses completed: overview, diseases_top, diseases_cost" <<<"$spark_output"
grep -q "Spark yearly trend available: False" <<<"$spark_output"

echo "Running Spark SQL through Hive Metastore 4.1..."
spark_hive_output="$(
  docker compose --profile tools run --rm --no-deps spark-client \
    /opt/spark/bin/spark-submit --master 'local[*]' \
    --conf spark.hadoop.fs.defaultFS=hdfs://namenode:8020 \
    --conf spark.sql.hive.metastore.version=4.1.0 \
    --conf spark.sql.hive.metastore.jars=maven \
    --conf 'spark.driver.extraJavaOptions=-Duser.home=/tmp -Divy.default.ivy.user.dir=/tmp/.ivy2' \
    /opt/medical/jobs/verify_hive.py 2>&1
)"
printf '%s\n' "$spark_hive_output"
grep -q "Spark Hive records: 2,094,483" <<<"$spark_hive_output"
grep -q "Spark Hive facility count: 205" <<<"$spark_hive_output"

echo "Phase 2A big-data consistency checks passed."
