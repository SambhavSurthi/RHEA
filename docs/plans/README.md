# plans/ — Design proposals before code

Every non-trivial change starts as a plan. A "non-trivial" change touches retrieval logic, agent/memory behaviour, security/RBAC, API contracts, schema, dependencies, infrastructure or UI patterns.

## Rules

- Filename: `RHEA-XXX-<kebab-title>.md`, matching a linked issue when one exists.
- Copy `TEMPLATE.md`; keep its sections.
- Status lifecycle: `draft` → `approved` → `implementing` → `done` / `superseded`.
- Only the project owner may mark a plan `approved`.
- No dependency additions or safety-invariant changes without an approved plan.
