"""Tool implementations: get_schema, run_sql, get_current_datetime.

Domain is restricted to the three denormalised STATS19 tables — collision,
vehicle, casualty. The DB also contains *_normalised (integer-coded)
counterparts, which get_schema never surfaces to the model (see
P6_implementation_plan.md §1: domain is "strictly" the three named tables).
"""

import re
import sqlite3
from datetime import datetime, timezone

from models import ColumnInfo, GetCurrentDatetimeResult, GetSchemaResult, TableSchema

DB_PATH = "data/road_safety.db"

DOMAIN_TABLES = ("collision", "vehicle", "casualty")

# Columns hidden from get_schema despite existing in the table: almost entirely
# unpopulated in this dataset (see data_gap.ipynb), so hiding them steers the
# model toward the coded alternative (local_authority_highway /
# local_authority_ons_district) that's actually populated for every year,
# rather than it discovering the gap turn by turn as in the Task 9 Q4/5 run.
EXCLUDED_COLUMNS = {
    "collision": {"local_authority_district"},
}

_WRITE_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "TRUNCATE", "GRANT", "REVOKE",
    "EXEC", "EXECUTE", "BEGIN", "COMMIT", "ROLLBACK",
)
_WRITE_KEYWORD_RE = re.compile(
    r"\b(" + "|".join(_WRITE_KEYWORDS) + r")\b", re.IGNORECASE
)


class SqlValidationError(ValueError):
    """Raised when a query fails code-level validation before execution."""


def validate_sql(query: str) -> None:
    """First line of defence: reject anything not a single, plain SELECT.

    The read-only connection (mode=ro) in run_sql is the hard backstop —
    this validator is belt-and-braces, and the thing deliberately attacked
    in the injection-attempt eval question.
    """
    stripped = query.strip()

    if not re.match(r"^SELECT\b", stripped, re.IGNORECASE):
        raise SqlValidationError("Only single SELECT statements are permitted.")

    # Allow one optional trailing semicolon, but reject any semicolon
    # elsewhere in the query (statement chaining).
    body = stripped[:-1] if stripped.endswith(";") else stripped
    if ";" in body:
        raise SqlValidationError("Statement chaining (';') is not permitted.")

    match = _WRITE_KEYWORD_RE.search(body)
    if match:
        raise SqlValidationError(
            f"Write/DDL keyword '{match.group(0)}' is not permitted."
        )


def run_sql(query: str, db_path: str = DB_PATH) -> list[dict]:
    """Execute a validated, read-only SELECT and return rows as dicts.

    Connection is opened read-only (file:...?mode=ro) as the hard backstop,
    and guaranteed to close on every path, including when execution raises.
    """
    validate_sql(query)

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _unique_keys(conn: sqlite3.Connection, table: str) -> list[list[str]]:
    """Composite unique keys for a table, e.g. casualty's (collision_index,
    vehicle_reference, casualty_reference) — so the model doesn't mistake a
    per-collision-scoped column (like casualty_reference alone) for a
    globally unique row identifier.
    """
    keys = []
    for index_name, is_unique in (
        (row[1], row[2]) for row in conn.execute(f"PRAGMA index_list({table})")
    ):
        if not is_unique:
            continue
        columns = [
            row[2]
            for row in sorted(
                conn.execute(f"PRAGMA index_info({index_name})"), key=lambda r: r[0]
            )
        ]
        keys.append(columns)
    return keys


def get_schema(db_path: str = DB_PATH) -> GetSchemaResult:
    """Introspect the three denormalised domain tables only."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = []
        for table in DOMAIN_TABLES:
            excluded = EXCLUDED_COLUMNS.get(table, set())
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [
                ColumnInfo(name=row[1], type=row[2])
                for row in cursor.fetchall()
                if row[1] not in excluded
            ]
            tables.append(
                TableSchema(
                    table=table, columns=columns, unique_keys=_unique_keys(conn, table)
                )
            )
        return GetSchemaResult(tables=tables)
    finally:
        conn.close()


def get_current_datetime() -> GetCurrentDatetimeResult:
    return GetCurrentDatetimeResult(datetime=datetime.now(timezone.utc).isoformat())
