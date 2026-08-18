from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..database import database_connection


class AnalyticsRepository:
    def __init__(self, config: Mapping[str, Any]):
        self.config = config

    @staticmethod
    def _where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        if filters.get("year") is not None:
            clauses.append("discharge_year = %s")
            values.append(filters["year"])
        if filters.get("age_group"):
            clauses.append("age_group = %s")
            values.append(filters["age_group"])
        if filters.get("hospital"):
            clauses.append("facility_name = %s")
            values.append(filters["hospital"])
        if filters.get("diagnosis"):
            clauses.append("(diagnosis_code = %s OR diagnosis_description LIKE %s)")
            values.extend([filters["diagnosis"], f"%{filters['diagnosis']}%"])
        return (" WHERE " + " AND ".join(clauses) if clauses else ""), values

    def _fetch_all(self, sql: str, values: list[Any]) -> list[dict[str, Any]]:
        with database_connection(self.config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, values)
                return list(cursor.fetchall())

    def _fetch_one(self, sql: str, values: list[Any]) -> dict[str, Any]:
        rows = self._fetch_all(sql, values)
        return rows[0] if rows else {}

    def ping(self) -> bool:
        return self._fetch_one("SELECT 1 AS ok", []).get("ok") == 1

    def overview(self, filters: dict[str, Any]) -> dict[str, Any]:
        where, values = self._where(filters)
        return self._fetch_one(
            """
            SELECT
                COUNT(*) AS total_records,
                COUNT(DISTINCT COALESCE(CAST(facility_id AS CHAR), facility_name)) AS facility_count,
                AVG(length_of_stay) AS avg_length_of_stay,
                AVG(total_charges) AS avg_total_charges,
                AVG(total_costs) AS avg_total_costs,
                AVG(CASE WHEN emergency_indicator = TRUE THEN 1.0 ELSE 0.0 END) AS emergency_ratio
            FROM hospital_discharges
            """ + where,
            values,
        )

    def _grouped(
        self,
        dimension_sql: str,
        dimension_alias: str,
        filters: dict[str, Any],
        limit: int,
        metrics_sql: str,
        order_sql: str,
        non_null_column: str,
    ) -> list[dict[str, Any]]:
        where, values = self._where(filters)
        non_null = f"{non_null_column} IS NOT NULL AND {non_null_column} <> ''"
        where += (" AND " if where else " WHERE ") + non_null
        sql = f"""
            SELECT {dimension_sql} AS {dimension_alias}, {metrics_sql}
            FROM hospital_discharges
            {where}
            GROUP BY {dimension_sql}
            ORDER BY {order_sql}
            LIMIT %s
        """
        return self._fetch_all(sql, [*values, limit])

    def diseases_top(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "diagnosis_description",
            "diagnosis",
            filters,
            limit,
            "COUNT(*) AS record_count",
            "record_count DESC, diagnosis ASC",
            "diagnosis_description",
        )

    def diseases_cost(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "diagnosis_description",
            "diagnosis",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(total_charges) AS avg_total_charges, AVG(total_costs) AS avg_total_costs",
            "avg_total_charges DESC, record_count DESC",
            "diagnosis_description",
        )

    def hospitals_top(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "facility_name",
            "hospital",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(length_of_stay) AS avg_length_of_stay",
            "record_count DESC, hospital ASC",
            "facility_name",
        )

    def hospitals_cost(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "facility_name",
            "hospital",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(total_charges) AS avg_total_charges, AVG(total_costs) AS avg_total_costs, AVG(length_of_stay) AS avg_length_of_stay",
            "avg_total_charges DESC, record_count DESC",
            "facility_name",
        )

    def age_distribution(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "age_group",
            "age_group",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(length_of_stay) AS avg_length_of_stay",
            "record_count DESC, age_group ASC",
            "age_group",
        )

    def age_cost(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "age_group",
            "age_group",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(total_charges) AS avg_total_charges, AVG(total_costs) AS avg_total_costs, AVG(length_of_stay) AS avg_length_of_stay",
            "age_group ASC",
            "age_group",
        )

    def payment_distribution(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        where, values = self._where(filters)
        where += (" AND " if where else " WHERE ") + "payment_type_1 IS NOT NULL AND payment_type_1 <> ''"
        return self._fetch_all(
            f"""
                SELECT payment_type_1 AS payment_type,
                       COUNT(*) AS record_count,
                       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS percentage
                FROM hospital_discharges
                {where}
                GROUP BY payment_type_1
                ORDER BY record_count DESC, payment_type ASC
                LIMIT %s
            """,
            [*values, limit],
        )

    def severity_distribution(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "severity",
            "severity",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(total_charges) AS avg_total_charges, AVG(length_of_stay) AS avg_length_of_stay",
            "record_count DESC, severity ASC",
            "severity",
        )

    def yearly_trends(self, filters: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        return self._grouped(
            "discharge_year",
            "year",
            filters,
            limit,
            "COUNT(*) AS record_count, AVG(total_charges) AS avg_total_charges, AVG(total_costs) AS avg_total_costs",
            "year ASC",
            "discharge_year",
        )
