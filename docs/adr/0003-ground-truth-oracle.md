# ADR-0003: Generator emits a defect manifest as test oracle

**Status:** Accepted · 2026-07-11

## Context
Reconciliation engines are usually tested with hand-written fixtures — a dozen cases, forever incomplete. We control the generator, so we can do better.

## Decision
The generator writes three artifacts per run: both ledger views **and** `defect_manifest.parquet` recording every injected defect (txn id, class, side, details). `recon verify` computes recall/precision per class by joining engine output against the manifest. Runs are fully seeded — same seed, same defects, byte-stable outputs.

## Consequences
- The headline metric is honest and mechanical: "rediscovers N% of injected defects, zero false positives on clean pairs."
- Property-style testing for free: CI runs multiple seeds and rates; a logic regression shows up as a recall drop, not a broken fixture.
- The manifest must never leak into the reconciler's inputs (enforced by directory layout: `data/input/` vs `data/oracle/`).
