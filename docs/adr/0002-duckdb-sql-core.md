# ADR-0002: DuckDB SQL as the matching core

**Status:** Accepted · 2026-07-11

## Context
The matching logic needs to run (a) locally over millions of rows, (b) in CI cheaply, and (c) inside a browser for the portfolio site's interactive demo.

## Decision
Every matching pass is a DuckDB SQL statement stored in `sql/` as numbered files; Python orchestrates (load → run passes → write outputs) without embedding logic. The browser demo executes the *same files* via DuckDB-WASM.

## Alternatives
- **Pandas/Polars:** logic gets trapped in dataframe code — not portable to the browser, harder to audit than SQL.
- **Spark:** wrong size; DuckDB does 10M-row joins on a laptop in seconds. The SQL remains portable to Spark if scale demands it.

## Consequences
- One source of truth for logic; the site demo cannot drift from the real engine.
- SQL must stay within DuckDB-WASM's feature set (no extensions beyond parquet).
- Python layer stays thin enough that the whole engine is understandable from `sql/` alone.
