---
uid: RHEA-001
title: Irrelevant retrieval, wrong answers and unverifiable citations
status: in_progress
severity: critical
assignee: rhea
created: 2026-11-26
updated: 2026-11-26
labels: [retrieval, generation, citations, security, evals]
area: retrieval
---

# RHEA-001 — Irrelevant retrieval, wrong answers and unverifiable citations

## Problem

Live probes against `POST /v1/query` show:

- a 3-hop question answered with the first hop only;
- an exact-fact question answered with unrelated chunks, with the correct source not retrieved;
- an unanswerable question answered confidently with fabricated `[n]` markers.

Evidence and root-cause IDs are in `docs/architecture-audit.md` §3–4 (P-01…P-22).

## Expected behaviour

Answers derive from canonical evidence, cite real chunks with correct pages, and abstain when evidence is insufficient.

## Steps to reproduce

1. Start stack: `powershell -ExecutionPolicy Bypass -File .\start-all.ps1`.
2. `POST /v1/query` with `"Which tool monitors the infrastructure that powers the Embedding Cache?"`.
3. Observe answer "Embedding Cache depends on the Redis Cluster [1]" instead of Datadog.

## Impact

Critical: the product cannot be trusted for research analysis. Citation display is decorative, not evidentiary. No document-level access control exists.

## Proposed approach

`docs/plans/RHEA-001-production-rag-rebuild.md` — phased rebuild beginning with the canonical document/chunk architecture. Do not start until the plan is `approved`.

## Acceptance criteria

- [ ] Stable chunk IDs shared by Postgres/Qdrant/OpenSearch/Neo4j/results/citations
- [ ] Docling structured parsing + OCR with page and element metadata
- [ ] Structural, token-aware, validated chunking
- [ ] BM25, dense and graph retrieval with provenance
- [ ] RRF + measured reranking
- [ ] Citation validity and entailment checks; no fabricated IDs
- [ ] Guardrails active; document ACLs enforced
- [ ] Reproducible evaluation with real retrieval/generation metrics
- [ ] All phases' exit tests executed and recorded

## Solution

<!-- Written only when all phases are complete and verified. -->

## Verification

<!-- Phase-by-phase results link back to session logs and audit evidence. -->
