# P6 — Claude Code Brief

Repo: **agentic-ai** (local and GitHub, matches this name exactly — not the `ai-programming-foundations-project-N` pattern used in earlier projects)

Read `P6_implementation_plan.md` in full before starting. It is the source of truth for every design decision below. If anything here is ambiguous or you find yourself needing to make a scope-affecting assumption (column restrictions, added fields, changed tool behaviour, altered safety logic, anything not explicitly specified) — stop and ask Simon rather than choosing a default.

**Division of labour:** you (Claude Code) own all implementation, execution, testing, and git operations below. You do **not** write the Agentic_AI_System_Design_Report.pdf, the architecture diagram, or any citation content — that's handled separately. Your job ends at working code, passing tests, populated logs, and a completed README.

**Standing process rules:**
- One commit per completed task, on `dev`, synced to `main` per usual workflow.
- After every task that produces runnable code, actually run it and report real, observed output — never assume or describe expected behaviour.
- The STATS19 SQLite database already exists in the data folder — it is too large to commit to the repo or submission zip. Do not attempt to commit it; add it to `.gitignore`. An extraction workbook already exists that can rebuild it from raw STATS19 files — the README must document that workbook as the reproduction path, not the DB file itself.

---

## Task 1 — Repo Setup
- Initialise/confirm `agentic-ai` repo, `dev` and `main` branches.
- Add `.gitignore` covering the SQLite DB file(s), any `__pycache__`, standard Python ignores.
- Skeleton `requirements.txt` (populated properly at the end, per Task 13 — don't `pip freeze` the whole environment).
- Commit.

## Task 2 — Confirm Data Access
- Locate the existing SQLite DB in the data folder. Confirm the three tables (collision, vehicle, casualty) and get a real look at actual column names/types — report these back, don't assume they match STATS19's published field names exactly, since this is denormalised.
- Confirm the extraction workbook exists and note its filename/location for the README.
- No commit needed unless notes are added to a scratch file — this is a verification step.

## Task 3 — Pydantic Models
- Define Pydantic models for: `run_sql` tool arguments, `get_schema` tool result shape, `get_current_datetime` tool result shape.
- Keep this thin — shape validation only, not business logic.
- Commit.

## Task 4 — Logging Database
- Build the `prompts` and `conversations` tables exactly as specified in the implementation plan (§8), in a separate SQLite file from the STATS19 data DB.
- Write a small init/migration script so the logging DB can be created fresh.
- Commit.

## Task 5 — Tool Implementations
- `get_schema`: introspects the STATS19 DB, returns table/column/type info.
- `run_sql`: read-only connection (`mode=ro`) as the hard backstop; code-level validation rejecting anything not a single `SELECT` (no chaining, no write keywords) as the first line of defence. Use context managers or `try`/`finally` to guarantee the connection always closes, including on exception paths.
- `get_current_datetime`: no arguments, returns current date/time.
- Commit.

## Task 6 — System Prompt v1
- Write the initial system prompt per implementation plan §7: scope/boundary statement, instruction to call `get_schema` before querying, instruction to use `get_current_datetime` for relative time language, at least two worked few-shot examples (a simple lookup and a cross-table join, showing question → tool calls → answer), explicit no-write/no-out-of-domain instruction.
- Insert as row 1 in `prompts`, `is_active = 1`.
- Commit.

## Task 7 — REPL Script
- Standalone `.py` script, `input()` loop.
- Calls the Anthropic Messages API directly via `requests` (no SDK) — construct the `tools` schema by hand from the Pydantic models, handle `stop_reason: tool_use` round-trips, send `tool_result` turns back correctly.
- Model: `claude-haiku-4-5-20251001`.
- Maintains the lightweight agent state object per implementation plan §5 (`conversation_id`, `schema_fetched`, `cached_schema`, `turn_number`) for the session — no rollback mechanism, this is intentional.
- Every turn (user input, assistant output, tool calls and results) logged to `conversations`, tagged with the active `prompt_id`.
- Run it manually yourself with a couple of throwaway questions to confirm the round-trip actually works end-to-end before moving on. Report what you observed.
- Commit.

## Task 8 — pytest Suite
Cover, at minimum:
- SQL validator rejects non-`SELECT` and chained/write statements
- Read-only connection genuinely cannot write
- Schema-cache logic only calls `get_schema` once per session
- Connections close on all paths, including when a query raises (mock/patch and assert `close()` is called)

Run the suite, report actual pass/fail output. Commit.

## Task 9 — Run the Evaluation Set
Run all 10 questions from implementation plan §10 through the actual REPL script, in order (question 5 depends on question 4's conversation context — run them in the same session). For each, capture and report:
- What the agent actually did (tool calls, in order, with arguments)
- What it actually answered
- Whether it matched expected behaviour or not — especially question 7 (did it call `get_schema` unprompted?), question 8 (did the injection attempt succeed or get blocked, and at which layer — validator or read-only connection?), question 9 (did it fabricate an answer or correctly say the data doesn't support the question?)

Do not editorialise or smooth over unexpected results — an observed failure here is useful content for the report, not a problem to hide. Commit the logged results.

## Task 10 — Testing Notebook
- Separate `.ipynb`. For each `conversation_id` produced in Task 9, reconstruct the full turn-by-turn exchange from the `conversations` table (joined to `prompts` for the active prompt version) and display it clearly.
- Under each reconstructed conversation, add a short Markdown cell with your own observation/recommendation (e.g. "agent skipped get_schema on first call, self-corrected after tool error — consider code-enforcing this if repeated" or "injection attempt blocked at validator layer, read-only connection never tested — consider a second attempt that bypasses the validator to test the backstop specifically"). These are a starting point for Simon's own review, not final conclusions.
- Confirm the notebook runs top-to-bottom cleanly.
- Commit.

## Task 11 — README
- Standard project description, what was built, dataset note.
- Reproduction path: extraction workbook must be run first to build the STATS19 SQLite DB (name it, note it's not included in the repo due to size), then the logging DB init script, then the REPL script.
- How to run the REPL script and the pytest suite.
- How to install dependencies.
- Commit.

## Task 12 — Docker
- Containerise per the engineering wraparound scope (Dockerfile, confirm it builds and the REPL script runs inside it). CI/CD is explicitly out of scope — note as a Future Extension, don't implement it.
- Commit.

## Task 13 — Final Reproducibility Check
- Build `requirements.txt` from the actual third-party imports used across the script/notebooks (hand-write or use `pipreqs`) — not a raw `pip freeze` of the whole environment.
- Confirm the REPL script, pytest suite, and testing notebook all run clean.
- Commit.

---

Report back after each task with what was actually run and what actually happened — this brief will inform the final report, so accuracy of what's reported matters more than a smooth narrative.
