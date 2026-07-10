# ADR-0001: Deterministic multi-pass matching, not ML scoring

**Status:** Accepted · 2026-07-11

## Context
Reconciliation must be **auditable**: every match and exception needs a defensible "why" for finance/regulatory review. Candidate approaches: deterministic rule passes vs. learned/fuzzy similarity scoring.

## Decision
Ordered deterministic passes (exact key → constrained fuzzy → classify), each recording its match reason. Ambiguity is surfaced as an exception, never resolved by a score threshold.

## Why
- Auditability beats recall-at-any-cost in money movement; a reconciler that "probably" matched two transactions is a liability.
- Determinism makes the engine testable against a ground-truth manifest — recall/precision per defect class are exact numbers, not estimates.
- Matches production practice at payment companies (contested exceptions go to humans, not models).

## Consequences
- Mangled references beyond the fuzzy pass's constraints stay unmatched (by design — they age into the exception queue).
- Rule changes require re-verification against the manifest; `recon verify` makes that one command.
