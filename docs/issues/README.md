# issues/ — Canonical tracker (RHEA-XXX)

One Markdown file per issue. This is the source of truth; no external tracker is assumed.

## Naming

`docs/issues/RHEA-XXX-<kebab-title>.md`, e.g. `RHEA-001-citation-drift.md`.
Next UID = highest existing `RHEA-*.md` (including `solved/`) + 1.

## Workflow

1. Copy `TEMPLATE.md`; fill frontmatter: `uid`, `title`, `status`, `severity`, `assignee`, `created`, `updated`, `labels`, `area`.
2. **Assign before solving:** set `assignee` and `status: in_progress` before any fix work.
3. Progress: `open` → `in_progress` → `review` → `closed`.
4. Write `## Solution` in the same file when fixed.
5. Move to `docs/issues/solved/` with `status: closed`. The moved file is the permanent record; do not delete it.

## Severity

| Level | Meaning |
|---|---|
| `critical` | Safety/RBAC/approval bypass, false-success, secret leak, data loss |
| `high` | Core retrieval, memory or citation correctness broken |
| `medium` | Degraded UX, flaky tests, non-blocking bugs |
| `low` | Docs, cosmetic, nice-to-have |

Never edit another handle's open issue without coordination.
