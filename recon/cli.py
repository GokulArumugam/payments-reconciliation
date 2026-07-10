"""Thin command line orchestration for the SQL reconciliation passes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import duckdb

from .generate import DEFAULT_RATES, DEFECT_CLASSES, generate


REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql"


def _sql_literal_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _render_sql(source: str, values: dict[str, Path]) -> str:
    for name, path in values.items():
        source = source.replace("{{" + name + "}}", _sql_literal_path(path))
    return source


def run(root: str | Path = ".") -> dict[str, Any]:
    """Execute the five SQL passes using only the two input ledger paths."""
    root = Path(root)
    switch_path = root / "data/input/switch_ledger.parquet"
    bank_path = root / "data/input/bank_settlement.parquet"
    if not switch_path.exists() or not bank_path.exists():
        raise FileNotFoundError("expected data/input/switch_ledger.parquet and bank_settlement.parquet")

    output_dir = root / "data/output"
    output_dir.mkdir(parents=True, exist_ok=True)
    matches_path = output_dir / "matches.parquet"
    exceptions_path = output_dir / "exceptions.parquet"
    summary_path = output_dir / "summary.json"
    for path in (matches_path, exceptions_path, summary_path, output_dir / "verification.json"):
        path.unlink(missing_ok=True)

    values = {
        "switch_path": switch_path,
        "bank_path": bank_path,
        "matches_path": matches_path,
        "exceptions_path": exceptions_path,
    }
    started = time.perf_counter()
    con = duckdb.connect(":memory:")
    try:
        for sql_path in sorted(SQL_DIR.glob("*.sql")):
            con.execute(_render_sql(sql_path.read_text(), values))
        switch_rows = con.execute("SELECT count(*) FROM switch_normalized").fetchone()[0]
        bank_rows = con.execute("SELECT count(*) FROM bank_normalized").fetchone()[0]
        match_rows = con.execute("SELECT count(*) FROM matches_final").fetchone()[0]
        exception_rows = con.execute("SELECT count(*) FROM exceptions_final").fetchone()[0]
        per_class = dict(
            con.execute(
                """
                SELECT detected_class, count(*)
                FROM (
                    SELECT detected_class FROM matches_final WHERE detected_class IS NOT NULL
                    UNION ALL
                    SELECT detected_class FROM exceptions_final WHERE detected_class IS NOT NULL
                )
                GROUP BY detected_class ORDER BY detected_class
                """
            ).fetchall()
        )
    finally:
        con.close()

    elapsed = time.perf_counter() - started
    summary = {
        "switch_rows": switch_rows,
        "bank_rows": bank_rows,
        "match_rows": match_rows,
        "exception_rows": exception_rows,
        "match_rate": (match_rows / switch_rows) if switch_rows else 0.0,
        "per_class_counts": per_class,
        "wall_clock_seconds": elapsed,
        "file_level_alarm": "BANK_INPUT_EMPTY" if bank_rows == 0 else None,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def verify(root: str | Path = ".") -> tuple[dict[str, Any], bool]:
    """Compare SQL outputs with the generator oracle; never used by ``run``."""
    root = Path(root)
    manifest_path = root / "data/oracle/defect_manifest.parquet"
    matches_path = root / "data/output/matches.parquet"
    exceptions_path = root / "data/output/exceptions.parquet"
    for path in (manifest_path, matches_path, exceptions_path):
        if not path.exists():
            raise FileNotFoundError(f"missing verification artifact: {path}")

    con = duckdb.connect(":memory:")
    try:
        manifest = _sql_literal_path(manifest_path)
        matches = _sql_literal_path(matches_path)
        exceptions = _sql_literal_path(exceptions_path)
        rows = con.execute(
            f"""
            WITH expected AS (
                SELECT DISTINCT txn_id, defect_class
                FROM read_parquet('{manifest}')
            ), actual AS (
                SELECT DISTINCT txn_id, detected_class AS defect_class
                FROM read_parquet('{matches}')
                WHERE detected_class IS NOT NULL
                UNION
                SELECT DISTINCT txn_id, detected_class AS defect_class
                FROM read_parquet('{exceptions}')
                WHERE detected_class IS NOT NULL
            ), classes AS (
                SELECT defect_class FROM expected
                UNION
                SELECT defect_class FROM actual
            )
            SELECT
                c.defect_class,
                (SELECT count(*) FROM expected e WHERE e.defect_class = c.defect_class) AS expected_count,
                (SELECT count(*) FROM actual a WHERE a.defect_class = c.defect_class) AS actual_count,
                (SELECT count(*) FROM expected e JOIN actual a USING (txn_id, defect_class)
                 WHERE e.defect_class = c.defect_class) AS true_positives,
                (SELECT count(*) FROM actual a LEFT JOIN expected e USING (txn_id, defect_class)
                 WHERE e.txn_id IS NULL AND a.defect_class = c.defect_class) AS false_positives
            FROM classes c
            ORDER BY c.defect_class
            """
        ).fetchall()
    finally:
        con.close()

    metrics: dict[str, dict[str, Any]] = {}
    total_false_positives = 0
    all_recall = True
    for defect_class, expected_count, actual_count, true_positives, false_positives in rows:
        recall = 1.0 if expected_count == 0 else true_positives / expected_count
        precision = 1.0 if actual_count == 0 and expected_count == 0 else (true_positives / actual_count if actual_count else 0.0)
        metrics[defect_class] = {
            "expected": expected_count,
            "actual": actual_count,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "recall": recall,
            "precision": precision,
        }
        total_false_positives += false_positives
        all_recall = all_recall and recall == 1.0
    report = {
        "per_class": metrics,
        "total_false_positives": total_false_positives,
        "passes": all_recall and total_false_positives == 0,
    }
    output_path = root / "data/output/verification.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report, bool(report["passes"])


def _rate_argument_name(defect_class: str) -> str:
    return "--rate-" + defect_class.lower().replace("_", "-")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="recon", description="Deterministic payment reconciliation")
    parser.add_argument("--root", default=".", help="directory containing data/ (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate_parser = subparsers.add_parser("generate", help="create seeded ledger views and oracle")
    generate_parser.add_argument("--seed", type=int, required=True)
    generate_parser.add_argument("--count", type=int, default=100_000)
    for defect_class in DEFECT_CLASSES:
        generate_parser.add_argument(_rate_argument_name(defect_class), dest=defect_class, type=float, default=DEFAULT_RATES[defect_class])
    subparsers.add_parser("run", help="reconcile the two input ledger views")
    subparsers.add_parser("verify", help="check reconciliation outputs against the oracle")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        rates = {name: getattr(args, name) for name in DEFECT_CLASSES}
        result = generate(seed=args.seed, count=args.count, rates=rates, root=args.root)
        print(json.dumps({"seed": args.seed, "count": args.count, "defects": result}, sort_keys=True))
        return
    if args.command == "run":
        print(json.dumps(run(args.root), indent=2, sort_keys=True))
        return
    report, passes = verify(args.root)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not passes:
        raise SystemExit(1)
