# agent-logs/ — Proof of work

Every AI agent session MUST leave a log here. This is the project's audit trail because the repository intentionally has no Git history.

## Rules

- One file per session: `<handle>/YYYY-MM-DD-HHmm.md`, timestamp = session **END** local time (24-hour).
- Create a new file; never edit or append to an existing one.
- Copy `TEMPLATE.md` and keep the exact header and section order.
- Record codebase-memory calls and outcomes, every command, every file changed, and verification results.
- Never include secrets, tokens or personal data.

## Supporting files

| File | Purpose |
|---|---|
| `TEMPLATE.md` | Exact session-log format |
| `CONTRIBUTORS.md` | Handle roster |
| `KNOWN_ISSUES.md` | Pre-existing or newly discovered failures that are not yet fixed |
| `<handle>/` | Per-contributor session files |
