"""pytest suite for agentic_system.py: schema-cache logic.

Covers the §5 agent-state requirement that get_schema is only ever
actually queried once per session, even if the model calls the tool
again later in the same conversation.
"""

from unittest.mock import patch

from agentic_system import AgentState, execute_tool
from models import ColumnInfo, GetSchemaResult, TableSchema


def test_schema_cache_only_calls_get_schema_once_per_session():
    fake_result = GetSchemaResult(
        tables=[TableSchema(table="collision", columns=[ColumnInfo(name="id", type="TEXT")])]
    )
    state = AgentState()

    with patch("agentic_system.get_schema", return_value=fake_result) as mock_get_schema:
        first_content, first_error = execute_tool("get_schema", {}, state)
        second_content, second_error = execute_tool("get_schema", {}, state)

    mock_get_schema.assert_called_once()
    assert first_error is False
    assert second_error is False
    assert first_content == second_content
    assert state.schema_fetched is True
    assert state.cached_schema == fake_result
