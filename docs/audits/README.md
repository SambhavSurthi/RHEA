# audits/ — Safety, security and incident record

Append-only record of anything that threatened RHEA's safety invariants: false-success reports, secret leaks, broken citation grounding, RBAC/approval bypass, data loss, or performance regressions.

## When to create an entry

Mandatory when a safety incident occurs (`AGENTRULES.md` §9), and recommended for red-team or performance reviews.

## Rules

- Filename: `YYYY-MM-DD-<slug>.md`.
- Copy `TEMPLATE.md`; keep the section order.
- Link a `docs/issues/RHEA-XXX-*.md` with `severity: critical` for incidents.
- Never rewrite or delete an existing audit; add corrections as new dated entries.
