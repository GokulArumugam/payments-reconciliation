# STATE — sprint handoff file

**Last updated:** 2026-07-11 — architecture phase (Claude)

Project 2 of Gokul's DE portfolio (see wiki-stream-pipeline for project 1; site: portfolio-site → gokularumugam-portfolio-site.vercel.app). Workflow: orchestrator designs/reviews; Codex implements (`--model gpt-5.6-terra --effort high`); everything verified live before acceptance.

## Status
- ✅ Architecture + ADRs 1-3: deterministic multi-pass matching, DuckDB-SQL core (same SQL reused by the site's browser demo via DuckDB-WASM), generator-emits-oracle testing model. **Binding.**
- ✅ Engine implemented (pending routine live verify on the target benchmark environment): seeded generator + isolated oracle, DuckDB-SQL multi-pass reconciler, thin `recon generate|run|verify` CLI, pytest correctness suite, Makefile, and diagram-first README.
- ⬜ Next: measured 1M/10M benchmark numbers into README; project page + in-browser site demo (reuses `sql/` files); final polish.

## Layout contract
- `data/input/` (ledger views only) vs `data/oracle/` (defect manifest — reconciler must never read).
- `sql/NN_name.sql` numbered passes, DuckDB-WASM-compatible SQL only (no extensions beyond parquet).

## Python env
python3.11 on host; `pip3 install duckdb` already present. Keep deps minimal: duckdb, pyarrow, click or argparse, pytest.
