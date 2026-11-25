# BRANDING.md — RHEA UI contract

Read this before creating or modifying any UI element in `frontend/streamlit_app.py`.

## Identity

- Product name: **RHEA — Research Hub for Exploration and Analysis**
- Short label: **RHEA**
- Voice: precise, research-oriented, calm. No marketing hype, no emoji-heavy copy in headings.

## Tokens

| Token | Value | Use |
|---|---|---|
| `rhea.ink` | `#111827` | Primary text |
| `rhea.muted` | `#6B7280` | Captions, secondary labels |
| `rhea.surface` | `#FFFFFF` | Cards and main surface |
| `rhea.surface_alt` | `#F8FAFC` | Sidebar / secondary panels |
| `rhea.accent` | `#2563EB` | Primary actions, active states |
| `rhea.accent_soft` | `#DBEAFE` | Selected/highlight backgrounds |
| `rhea.success` | `#16A34A` | Healthy states, trusted badge |
| `rhea.warning` | `#D97706` | Unverified badge |
| `rhea.danger` | `#DC2626` | Quarantined/flagged states |

No off-palette hex values. Use Streamlit native widgets (`st.chat_message`, `st.expander`, `st.status`, `st.file_uploader`) rather than hand-built primitives.

## Component rules

- Chat: user and assistant messages use `st.chat_message`; streamed tokens render progressively.
- Reasoning: one `st.status` panel per turn; steps are numbered, never nested.
- Citations: `[n]` in the answer maps to a numbered chip showing document, page, trust, retrieval type and hop distance.
- Upload: sidebar-only, multi-file, trust selector adjacent to the control.
- Memory: turn count and auto-summary indicator in the sidebar; "New chat" resets both UI and server thread.

## Immutables

Product name, accent color, citation mapping `[n] → chip`, and the requirement that every answer shows sources. Changes to these require owner approval and an update to this file in the same change set.
