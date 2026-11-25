# Getting started with RHEA

**Audience:** researcher
**Time required:** ~3 minutes
**Prerequisites:** the stack is running (`start-all.ps1`)

## Goal

Upload a paper, ask a question, and read an answer with a page-level citation.

## Steps

1. Open `http://127.0.0.1:8501`.
2. In the sidebar, choose one or more PDFs under **Upload a PDF** and keep trust as `trusted`.
3. Click **Embed + index PDFs**. A success message shows pages, chunks, entities and relations.
4. In the chat box, ask a specific question, e.g. *"What does the inference gateway depend on?"*
5. Watch the answer stream in. Expand **Agent reasoning** to see retrieval and fusion steps.

## How to verify success

- The answer ends claims with `[1]`, `[2]`, etc.
- Numbered citation chips below the answer show document name and page number.
- The sidebar shows a turn count that grows after each question.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| API offline in sidebar | API not running or on another port | Re-run `start-all.ps1` and use the printed URL |
| Upload fails with 401 | Wrong writer key | Enter the writer key from `.env` in the sidebar |
| No citations | No documents indexed | Upload a PDF first |

## Related

See `docs/runbooks/` for operational procedures and `docs/plans/` for proposed changes.
