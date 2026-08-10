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


def get_schema(db_path: str = DB_PATH) -> GetSchemaResult:
    """Introspect the three denormalised domain tables only."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = []
        for table in DOMAIN_TABLES:
            cursor = conn.execute(f"PRAGMA table_info({table})")
            columns = [
                ColumnInfo(name=row[1], type=row[2]) for row in cursor.fetchall()
            ]
            tables.append(TableSchema(table=table, columns=columns))
        return GetSchemaResult(tables=tables)
    finally:
        conn.close()


def get_current_datetime() -> GetCurrentDatetimeResult:
    return GetCurrentDatetimeResult(datetime=datetime.now(timezone.utc).isoformat())
