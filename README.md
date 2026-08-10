# agentic-ai — STATS19 Query Agent

A single-agent, REPL-style, read-only natural-language question-answering system over
the UK Department for Transport's STATS19 road traffic collision data. Built for AI
Masters capstone project P6. Full design rationale is in `P6_implementation_plan.md`;
the task-by-task build brief is in `P6_claude_code_brief.md`.

## What this is

- A REPL script that answers questions about UK road collisions by generating and
  running read-only SQL against a local SQLite database, via the Anthropic Messages
  API (`claude-haiku-4-5-20251001`), called directly with `requests` — no `anthropic`
  SDK. Tool-calling (schema construction, `stop_reason: tool_use` round-trips,
  `tool_result` turns) is all hand-implemented.
- The agent cannot write, update, or delete data under any circumstance, and refuses
  questions outside the collision/vehicle/casualty domain or unsupported by the data.
- Every turn of every conversation is logged to a local SQLite logging database,
  tagged with the system prompt version that produced it.

## Dataset

STATS19 Road Safety Collision Data — the UK Department for Transport's official road
traffic collision database, pre-curated "last 5 years" extract (collision years
2021–2025 inclusive): <https://www.gov.uk/government/statistical-data-sets/road-safety-open-data>

Three source tables (collision, vehicle, casualty) are ingested and denormalised into
a single SQLite database, `data/road_safety.db`, by `full_ingestion.ipynb`. That
database actually contains **6 tables**: the denormalised `collision`/`vehicle`/
`casualty` tables (decoded text values — the agent's query surface) plus
`collision_normalised`/`vehicle_normalised`/`casualty_normalised` (integer-coded
counterparts, used during ingestion). The agent's `get_schema` tool only ever exposes
the 3 denormalised tables.

`data/road_safety.db` (~1.3GB) and the raw CSVs in `data/raw/` (~243MB combined) are
**not included in this repo or any submission zip** — too large. See Reproduction
below.

## What was built

| File | Purpose |
|---|---|
| `models.py` | Pydantic models for tool argument/result shape validation |
| `tools.py` | `get_schema`, `run_sql` (validator + read-only connection), `get_current_datetime` |
| `init_logging_db.py` | Creates the logging DB (`prompts`, `conversations` tables) |
| `seed_system_prompt.py` | Inserts and activates system prompt v1 |
| `repl.py` | The REPL agent itself |
| `test_tools.py`, `test_repl.py` | pytest suite |
| `testing.ipynb` | Workbench notebook: reconstructs logged conversations from the Task 9 evaluation run, with observations |
| `logging.db` | Populated logging DB from the evaluation run (tracked in git — it's KBs, not a large-data problem) |

Docker containerisation (implementation plan §12) was **not implemented** — dropped
per a standing "no Docker in any capstone project" constraint, noted as a Future
Extension in the design report rather than attempted.

## Reproduction

1. **Get the raw STATS19 CSVs.** Download the "last 5 years" collision, vehicle, and
   casualty extracts from the DfT link above into `data/raw/` (filenames expected by
   `full_ingestion.ipynb`:
   `dft-road-casualty-statistics-{collision,vehicle,casualty}-last-5-years.csv`).
2. **Build the STATS19 database.** Run `full_ingestion.ipynb` top-to-bottom. This
   produces `data/road_safety.db` (~1.3GB, gitignored).
3. **Initialise the logging database and seed the system prompt** (skip if you want
   to keep the evaluation-run `logging.db` already in the repo):
   ```
   python init_logging_db.py
   python seed_system_prompt.py
   ```
4. **Set your API key** — create a `.env` file in the project root:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

## Running the REPL

```
python repl.py
```

Type a question, get an answer; Ctrl-D to exit. Each session gets a fresh
`conversation_id` and starts with no cached schema.

## Running the tests

```
pytest -v
```

17 tests covering SQL validation (rejects non-`SELECT`, chained statements, write
keywords), the read-only connection genuinely refusing writes, connection cleanup on
both success and exception paths, and schema-cache behaviour (only queried once per
session).

## Installing dependencies

```
python -m venv .venv && source .venv/bin/activate   # or use an existing venv
pip install -r requirements.txt
```

`requirements.txt` is generated from actual imports (`pipreqs --scan-notebooks`), not
a full environment freeze — see Task 13 notes in the build brief for how it was
produced and cross-checked.
