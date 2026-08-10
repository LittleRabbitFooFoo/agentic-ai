"""Standalone REPL for the STATS19 query agent.

Talks to the Anthropic Messages API directly via `requests` (no SDK):
builds the `tools` schema by hand from the Pydantic models in models.py,
handles `stop_reason: tool_use` round-trips manually, and sends
`tool_result` turns back itself. Model: claude-haiku-4-5-20251001.

Agent state (§5 of the implementation plan) is a lightweight in-memory
object scoped to one conversation_id — no rollback, by design. Every
turn (user input, assistant text, tool calls, tool results) is logged to
the `conversations` table, tagged with whichever `prompts` row is active.
"""

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests
from pydantic import ValidationError

from init_logging_db import LOGGING_DB_PATH
from models import GetSchemaResult, RunSqlArgs
from tools import SqlValidationError, get_current_datetime, get_schema, run_sql

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
MAX_TOOL_ROUNDS = 10  # safety valve against runaway tool-call loops

TOOLS = [
    {
        "name": "get_schema",
        "description": (
            "Returns table and column names/types for the collision, vehicle, "
            "and casualty tables. Call this before your first query in a "
            "conversation."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "run_sql",
        "description": (
            "Executes a single read-only SELECT statement against the STATS19 "
            "database and returns the resulting rows."
        ),
        "input_schema": RunSqlArgs.model_json_schema(),
    },
    {
        "name": "get_current_datetime",
        "description": (
            "Returns the current date/time. Use this to resolve relative time "
            "language (e.g. 'last year') to an actual year/date."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


def load_env(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class AgentState:
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schema_fetched: bool = False
    cached_schema: GetSchemaResult | None = None
    turn_number: int = 0


def get_active_prompt(db_path: str = LOGGING_DB_PATH) -> tuple[int, str]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, content FROM prompts WHERE is_active = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError(
                "No active system prompt found — run seed_system_prompt.py first."
            )
        return row[0], row[1]
    finally:
        conn.close()


def log_turn(
    conversation_id: str,
    turn_number: int,
    role: str,
    content: str,
    prompt_id: int,
    db_path: str = LOGGING_DB_PATH,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO conversations "
            "(conversation_id, turn_number, role, content, prompt_id, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                turn_number,
                role,
                content,
                prompt_id,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def execute_tool(name: str, tool_input: dict, state: AgentState) -> tuple[str, bool]:
    """Runs a tool call. Returns (result_content_as_string, is_error)."""
    try:
        if name == "get_schema":
            if state.schema_fetched:
                result = state.cached_schema
            else:
                result = get_schema()
                state.cached_schema = result
                state.schema_fetched = True
            return result.model_dump_json(), False

        if name == "run_sql":
            args = RunSqlArgs.model_validate(tool_input)
            rows = run_sql(args.query)
            return json.dumps(rows), False

        if name == "get_current_datetime":
            result = get_current_datetime()
            return result.model_dump_json(), False

        return f"Unknown tool: {name}", True

    except (ValidationError, SqlValidationError) as e:
        return str(e), True
    except sqlite3.Error as e:
        return f"Database error: {e}", True


def call_api(system_prompt: str, messages: list) -> dict:
    api_key = os.environ["ANTHROPIC_API_KEY"]
    response = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": messages,
            "tools": TOOLS,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def run_turn(
    user_input: str,
    messages: list,
    system_prompt: str,
    prompt_id: int,
    state: AgentState,
) -> str:
    state.turn_number += 1
    log_turn(state.conversation_id, state.turn_number, "user", user_input, prompt_id)
    messages.append({"role": "user", "content": user_input})

    final_text = ""
    for _ in range(MAX_TOOL_ROUNDS):
        response = call_api(system_prompt, messages)
        content_blocks = response["content"]
        messages.append({"role": "assistant", "content": content_blocks})

        for block in content_blocks:
            if block["type"] == "text" and block["text"]:
                final_text = block["text"]
                log_turn(
                    state.conversation_id,
                    state.turn_number,
                    "assistant",
                    block["text"],
                    prompt_id,
                )

        if response["stop_reason"] != "tool_use":
            return final_text

        tool_results = []
        for block in content_blocks:
            if block["type"] != "tool_use":
                continue
            log_turn(
                state.conversation_id,
                state.turn_number,
                "assistant",
                json.dumps({"tool_call": block["name"], "input": block["input"]}),
                prompt_id,
            )
            result_content, is_error = execute_tool(block["name"], block["input"], state)
            log_turn(
                state.conversation_id,
                state.turn_number,
                "tool",
                json.dumps(
                    {"tool_name": block["name"], "result": result_content, "is_error": is_error}
                ),
                prompt_id,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": result_content,
                    "is_error": is_error,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return final_text or "(no response — tool round-trip limit reached)"


def main() -> None:
    load_env()
    if "ANTHROPIC_API_KEY" not in os.environ:
        raise RuntimeError("ANTHROPIC_API_KEY not set (checked .env and environment).")

    prompt_id, system_prompt = get_active_prompt()
    state = AgentState()
    messages: list = []

    print(f"STATS19 query agent (conversation_id={state.conversation_id}). Ctrl-D to exit.")
    while True:
        try:
            user_input = input("> ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        answer = run_turn(user_input, messages, system_prompt, prompt_id, state)
        print(answer)


if __name__ == "__main__":
    main()
