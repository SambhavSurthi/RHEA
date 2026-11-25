# NAVIGATION.md — Read order and what-lives-where

## Read order for a new agent

1. `AGENTS.md` — how to work in this codebase.
2. `AGENTRULES.md` — mandatory behavior, verification, logging, memory-first retrieval.
3. `README.md` — product purpose, architecture and quick start.
4. `docs/STRUCTURE.md` — module ownership and data flow.
5. `docs/BRANDING.md` — **only if touching the UI**.
6. `docs/agent-logs/README.md` — how to log your session.
7. `docs/issues/README.md` and `docs/plans/README.md` — how changes are tracked.
8. `docs/PROJECT_REPORT.md` — deeper engineering context when needed.
9. `docs/architecture-audit.md` — verified root causes and live probe evidence (Phase 1).
10. `docs/plans/RHEA-001-production-rag-rebuild.md` — the approved sequence of work.

## What lives where

| Need | Go to |
|---|---|
| Start/stop the system | `start-all.ps1`, `stop-all.ps1`, `docs/runbooks/` |
| Understand retrieval | `backend/rhea/pipelines/retrieval.py`, `docs/STRUCTURE.md` |
| Understand chat/memory | `backend/rhea/services/chat.py`, `docs/architecture-decisions.md` |
| Change an API endpoint | `backend/rhea/api/`, `docs/plans/` |
| Change the UI | `frontend/streamlit_app.py`, `docs/BRANDING.md` |
| Report a bug / propose work | `docs/issues/` |
| Design a non-trivial change | `docs/plans/` |
| Record an incident | `docs/audits/` |
| Prove what you did | `docs/agent-logs/` |
| Learn how to use RHEA | `docs/user-guide/` |
| Understand why retrieval is wrong today | `docs/architecture-audit.md` |
| Follow the production rebuild | `docs/issues/RHEA-001-*.md`, `docs/plans/RHEA-001-*.md` |

## Maintenance

When adding, moving or renaming a documentation area, update this file in the same change. Broken links are a verification failure (`AGENTRULES.md` §4).
