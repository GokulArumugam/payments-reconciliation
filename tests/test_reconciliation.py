from __future__ import annotations

from datetime import datetime, date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from recon.cli import run, verify
from recon.generate import DEFECT_CLASSES, LEDGER_SCHEMA, generate


def _rates_for_only(defect_class: str) -> dict[str, float]:
    return {name: (0.01 if name == defect_class else 0.0) for name in DEFECT_CLASSES}


def _detected(root: Path) -> list[tuple[int, str]]:
    import duckdb

    return duckdb.sql(
        f"""
        SELECT txn_id, detected_class
        FROM read_parquet('{root / 'data/output/matches.parquet'}')
        WHERE detected_class IS NOT NULL
        UNION ALL
        SELECT txn_id, detected_class
        FROM read_parquet('{root / 'data/output/exceptions.parquet'}')
        WHERE detected_class IS NOT NULL
        """
    ).fetchall()


def test_generator_is_byte_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    generate(seed=1234, count=250, root=first)
    generate(seed=1234, count=250, root=second)
    for relative in (
        "data/input/switch_ledger.parquet",
        "data/input/bank_settlement.parquet",
        "data/oracle/defect_manifest.parquet",
    ):
        assert (first / relative).read_bytes() == (second / relative).read_bytes()


@pytest.mark.parametrize("defect_class", DEFECT_CLASSES)
def test_each_defect_class_is_detected_in_isolation(tmp_path: Path, defect_class: str) -> None:
    root = tmp_path / defect_class.lower()
    generate(seed=91, count=100, rates=_rates_for_only(defect_class), root=root)
    run(root)
    report, passed = verify(root)
    assert passed, report
    assert report["per_class"][defect_class]["expected"] == 1
    assert report["per_class"][defect_class]["recall"] == 1.0
    detected = _detected(root)
    assert len(detected) == 1
    assert detected[0][1] == defect_class


def test_duplicate_on_both_sides_is_one_duplicate_exception(tmp_path: Path) -> None:
    root = tmp_path / "both-duplicate"
    generate(seed=3, count=1, rates={name: 0.0 for name in DEFECT_CLASSES}, root=root)
    for filename, prefix in (("switch_ledger.parquet", "S"), ("bank_settlement.parquet", "B")):
        path = root / "data/input" / filename
        rows = pq.read_table(path).to_pylist()
        duplicate = dict(rows[0])
        duplicate["record_id"] = f"{prefix}-000000000001-DUP"
        pq.write_table(pa.Table.from_pylist(rows + [duplicate], schema=LEDGER_SCHEMA), path, compression="zstd")
    run(root)
    import duckdb

    result = duckdb.sql(
        f"SELECT exception_class, side FROM read_parquet('{root / 'data/output/exceptions.parquet'}')"
    ).fetchall()
    assert result == [("DUPLICATE", "BOTH")]


def _write_ambiguous_fixture(root: Path) -> None:
    common = {
        "amount_minor": 100,
        "currency": "INR",
        "status": "SETTLED",
        "counterparty": "ACME-RETAIL-12345",
        "txn_time": datetime(2024, 1, 1, 9, 0),
        "settlement_date": date(2024, 1, 1),
    }
    switch = [{**common, "record_id": "S-1", "txn_id": 1, "utr": "UTR-SWITCH-ONE"}]
    bank = [
        {**common, "record_id": "B-1", "txn_id": 11, "utr": "UTR-BANK-ONE"},
        {**common, "record_id": "B-2", "txn_id": 12, "utr": "UTR-BANK-TWO"},
    ]
    (root / "data/input").mkdir(parents=True)
    pq.write_table(pa.Table.from_pylist(switch, schema=LEDGER_SCHEMA), root / "data/input/switch_ledger.parquet")
    pq.write_table(pa.Table.from_pylist(bank, schema=LEDGER_SCHEMA), root / "data/input/bank_settlement.parquet")


def test_ambiguous_fuzzy_candidate_surfaces_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "ambiguous"
    _write_ambiguous_fixture(root)
    run(root)
    import duckdb

    classes = duckdb.sql(
        f"SELECT exception_class FROM read_parquet('{root / 'data/output/exceptions.parquet'}')"
    ).fetchall()
    assert classes == [("AMBIGUOUS",)]


@pytest.mark.parametrize("seed", [7, 42, 2026])
def test_default_rates_verify_across_seeds(tmp_path: Path, seed: int) -> None:
    root = tmp_path / f"seed-{seed}"
    generate(seed=seed, root=root)
    run(root)
    report, passed = verify(root)
    assert passed, report
