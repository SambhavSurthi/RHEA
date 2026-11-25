# Runbook: <title>

- **Owner / last verified by:**
- **Last verified:** YYYY-MM-DD
- **Trigger:** <!-- when to use this runbook -->

## Preconditions

- [ ] Confirm no secret values will be printed.
- [ ] Confirm current state with codebase-memory (`list_projects`, `index_status`).
- [ ] Note the current verification baseline (`pytest -q`, `ruff check`).

## Steps

1. Command / action → expected result.
2. Command / action → expected result.
3.

## Verification

- [ ] `pytest -q`: pass
- [ ] `ruff check ...`: pass
- [ ] `/health` reports expected backends
- [ ] Session log written to `docs/agent-logs/`

## Rollback

Exact steps to return to the pre-runbook state, including data-volume implications.

## Notes / incident link

<!-- Link docs/audits/ entry if this runbook was created because of an incident. -->
