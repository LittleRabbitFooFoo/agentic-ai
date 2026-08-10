"""pytest suite for tools.py: SQL validation and connection safety.

Uses a throwaway temp SQLite DB rather than the real (gitignored,
1.3GB) STATS19 DB, so these tests are self-contained and reproducible
in a fresh clone without the data present.
"""

import sqlite3
from unittest.mock import MagicMock, patch

import pytest

import tools
from tools import SqlValidationError, get_current_datetime, get_schema, run_sql, validate_sql


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "temp.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE t (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture
def domain_shaped_db(tmp_path):
    """A minimal DB with the real collision/vehicle/casualty table names and
    the same composite unique indexes as the actual STATS19 DB, so
    get_schema's key-detection logic can be tested without the real
    (gitignored) 1.3GB database.
    """
    db_path = tmp_path / "domain.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE collision (
            collision_index TEXT, collision_year INTEGER, local_authority_district TEXT
        );
        CREATE UNIQUE INDEX idx_collision_key ON collision(collision_index);

        CREATE TABLE vehicle (collision_index TEXT, vehicle_reference INTEGER);
        CREATE UNIQUE INDEX idx_vehicle_key ON vehicle(collision_index, vehicle_reference);

        CREATE TABLE casualty (
            collision_index TEXT, vehicle_reference INTEGER, casualty_reference INTEGER
        );
        CREATE UNIQUE INDEX idx_casualty_key
            ON casualty(collision_index, vehicle_reference, casualty_reference);
        """
    )
    conn.commit()
    conn.close()
    return str(db_path)


# --- SQL validator ---------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM collision",
        "UPDATE collision SET collision_year = 1",
        "DROP TABLE collision",
        "INSERT INTO collision VALUES (1)",
        "not even sql",
    ],
)
def test_validate_sql_rejects_non_select(query):
    with pytest.raises(SqlValidationError):
        validate_sql(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM collision; DROP TABLE collision",
        "SELECT * FROM collision WHERE x = 1; DELETE FROM collision",
    ],
)
def test_validate_sql_rejects_chained_statements(query):
    with pytest.raises(SqlValidationError):
        validate_sql(query)


def test_validate_sql_rejects_write_keyword_even_when_prefixed_by_select():
    with pytest.raises(SqlValidationError):
        validate_sql("SELECT * FROM t WHERE 1=1; UPDATE t SET name = 'x'")


def test_validate_sql_accepts_plain_select():
    validate_sql("SELECT * FROM collision WHERE collision_year = 2023")


def test_validate_sql_accepts_single_trailing_semicolon():
    validate_sql("SELECT 1;")


def test_validate_sql_does_not_false_positive_on_substring_keywords():
    # "created_at"-style column names must not trip the CREATE keyword check
    validate_sql("SELECT created_at FROM t")


# --- Read-only connection backstop -----------------------------------------


def test_read_only_connection_genuinely_cannot_write(temp_db):
    conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO t VALUES (3, 'c')")
    finally:
        conn.close()


def test_run_sql_returns_rows(temp_db):
    rows = run_sql("SELECT * FROM t ORDER BY id", db_path=temp_db)
    assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]


# --- Connection closes on all paths -----------------------------------------


def test_run_sql_closes_connection_on_success(temp_db):
    # sqlite3.Connection's methods are read-only (C extension type), so it
    # can't be spied on directly — fully mock it instead, with fetchall()
    # returning pre-shaped dict rows so `dict(row)` in run_sql still works.
    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [{"id": 1, "name": "a"}]

    with patch.object(tools.sqlite3, "connect", return_value=mock_conn) as mock_connect:
        rows = run_sql("SELECT * FROM t", db_path=temp_db)

    mock_connect.assert_called_once()
    mock_conn.close.assert_called_once()
    assert rows == [{"id": 1, "name": "a"}]


def test_run_sql_closes_connection_when_query_raises(temp_db):
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = sqlite3.OperationalError("boom")

    with patch.object(tools.sqlite3, "connect", return_value=mock_conn):
        with pytest.raises(sqlite3.OperationalError):
            run_sql("SELECT * FROM t", db_path=temp_db)

    mock_conn.close.assert_called_once()


def test_get_current_datetime_returns_iso_string():
    result = get_current_datetime()
    assert "T" in result.datetime


# --- get_schema surfaces composite unique keys ------------------------------


def test_get_schema_reports_composite_unique_keys(domain_shaped_db):
    result = get_schema(db_path=domain_shaped_db)
    keys_by_table = {t.table: t.unique_keys for t in result.tables}

    assert keys_by_table["collision"] == [["collision_index"]]
    assert keys_by_table["vehicle"] == [["collision_index", "vehicle_reference"]]
    assert keys_by_table["casualty"] == [
        ["collision_index", "vehicle_reference", "casualty_reference"]
    ]


def test_get_schema_hides_local_authority_district(domain_shaped_db):
    # Populated for only 194 of 513,801 collision rows in the real dataset — hidden
    # so the model uses local_authority_highway/ons_district instead.
    result = get_schema(db_path=domain_shaped_db)
    collision_columns = next(t.columns for t in result.tables if t.table == "collision")
    column_names = [c.name for c in collision_columns]

    assert "local_authority_district" not in column_names
    assert "collision_index" in column_names  # sanity check: other columns unaffected
