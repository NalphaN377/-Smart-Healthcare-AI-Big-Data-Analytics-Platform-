from pathlib import Path
from xml.etree import ElementTree

from backend.app.utils.columns import OUTPUT_COLUMNS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _properties(path: Path) -> dict[str, str]:
    root = ElementTree.parse(path).getroot()
    return {
        property_node.findtext("name", ""): property_node.findtext("value", "")
        for property_node in root.findall("property")
    }


def test_hdfs_is_single_replica_and_uses_docker_volumes():
    properties = _properties(PROJECT_ROOT / "docker" / "hadoop" / "hdfs-site.xml")
    assert properties["dfs.replication"] == "1"
    assert properties["dfs.namenode.name.dir"] == "file:///data/name"
    assert properties["dfs.datanode.data.dir"] == "file:///data/data"


def test_hive_external_table_matches_clean_parquet_contract():
    ddl = (PROJECT_ROOT / "docker" / "hive" / "init.sql").read_text(encoding="utf-8")
    assert "CREATE EXTERNAL TABLE IF NOT EXISTS" in ddl
    assert "external.table.purge'='false" in ddl
    assert "hdfs://namenode:8020/medical/processed/hospital_discharges" in ddl
    for column in OUTPUT_COLUMNS:
        assert f"  {column} " in ddl


def test_hive_facility_count_uses_trimmed_non_empty_names():
    sql = (PROJECT_ROOT / "docker" / "hive" / "verify.sql").read_text(encoding="utf-8")
    assert "COUNT(DISTINCT CASE" in sql
    assert "TRIM(facility_name) <> ''" in sql
    assert "THEN TRIM(facility_name)" in sql
