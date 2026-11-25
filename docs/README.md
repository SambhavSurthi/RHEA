# docs/ — Project knowledge base

This folder is the single source of truth for how RHEA is designed, operated, tracked and improved. Nothing here is decorative: every area has a defined purpose and a required format.

| Path | Why it exists | What goes here |
|---|---|---|
| `NAVIGATION.md` | Read order and map | Start here; links to every doc area |
| `STRUCTURE.md` | Module ownership | Package layout, boundaries, data flow |
| `PROJECT_REPORT.md` | Engineering report | What the system is, how it works, how to use it |
| `BRANDING.md` | UI contract | Tokens and integrity rules for the Streamlit UI |
| `architecture-decisions.md` | ADRs | Why hybrid retrieval, RRF, local fallback, LangGraph |
| `architecture-audit.md` | Phase 1 audit | Verified root causes, live probe evidence, what to preserve |
| `production-hardening.md` | Production checklist | What is implemented and what remains |
| `agent-logs/` | Proof of work | One mandatory session log per agent session |
| `audits/` | Incident record | Safety/red-team/performance audits and findings |
| `issues/` | Canonical tracker | `RHEA-XXX` issues, open and solved |
| `plans/` | Change proposals | Non-trivial changes are designed before implementation |
| `runbooks/` | Operations | Repeatable procedures (start/stop, rollback, eval) |
| `user-guide/` | End-user docs | How a researcher uses RHEA |

This knowledge base is **living**: when architecture, folders, tools, libraries or behaviour change, every affected file here and in `AGENTS.md` / `AGENTRULES.md` / `README.md` must be updated in the same change set, then codebase memory re-indexed. See `AGENTS.md` §11.

Rules for writing here:

- Use relative, lowercase-hyphen filenames.
- Link every new doc area from `NAVIGATION.md`.
- Copy the relevant `TEMPLATE.md` before creating a new file.
- Never put secrets, tokens or personal data in any document.
