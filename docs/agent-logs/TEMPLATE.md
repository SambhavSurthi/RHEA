## YYYY-MM-DD HH:mm | agent: <agent-name> | tool: <tool> | model: <model-id>

**Task:** One paragraph — what this session was asked to do.

**Actions:**
1. Read `AGENTS.md`, `AGENTRULES.md`, `docs/NAVIGATION.md`.
2. codebase-memory: `list_projects` → `<result>`; `index_repository(rhea)` → `<result>`.
3. codebase-memory: `search_graph` / `get_architecture` / `get_code_snippet` → `<what was found>`.
4. Files read: `<paths>`.
5. Commands run: `<command>` → `<exit code / outcome>`.
6. Files written/moved/deleted: `<paths>`.
7. Verification commands and their outcomes: `<commands>`.
8. Sub-agents used: `<persona, scope, outcome>` or `none`.

**Files changed:**
- Add: `<paths>`
- Modify: `<paths>`
- Move: `<from> → <to>`
- Delete: `<paths>`

**Verification:**
- `pytest -q`: `<pass/fail, count>`
- `ruff check ...`: `<pass/fail>`
- `scripts/check.ps1`: `<pass/fail>`
- Integration / UI / eval: `<pass/fail with what was exercised>`
- codebase-memory re-indexed after changes: `<yes/no + result>`

**Decisions / rationale:** Why the change was made; alternatives rejected; invariants preserved.

**Follow-ups:** Unfinished work, discovered issues, risks for the next agent. Write `none` if none.
