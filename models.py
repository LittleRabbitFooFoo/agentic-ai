"""Pydantic models for tool-call argument/result shape validation.

Thin by design: shape validation only, no business logic. Business rules
(read-only enforcement, SQL statement validation) live in tools.py.
"""

from pydantic import BaseModel


class RunSqlArgs(BaseModel):
    query: str


class ColumnInfo(BaseModel):
    name: str
    type: str


class TableSchema(BaseModel):
    table: str
    columns: list[ColumnInfo]


class GetSchemaResult(BaseModel):
    tables: list[TableSchema]


class GetCurrentDatetimeResult(BaseModel):
    datetime: str
