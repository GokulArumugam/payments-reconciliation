"""Seeded synthetic payment data and defect-oracle generator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import random
from typing import Mapping

import pyarrow as pa
import pyarrow.parquet as pq


DEFECT_CLASSES = (
    "MISSING_IN_BANK",
    "MISSING_IN_SWITCH",
    "DUPLICATE",
    "AMOUNT_MISMATCH",
    "STATUS_MISMATCH",
    "LATE_SETTLEMENT",
    "REFERENCE_MANGLED",
)
DEFAULT_RATES = {defect: 0.005 for defect in DEFECT_CLASSES}

LEDGER_SCHEMA = pa.schema(
    [
        pa.field("record_id", pa.string()),
        pa.field("txn_id", pa.int64()),
        pa.field("utr", pa.string()),
        pa.field("amount_minor", pa.int64()),
        pa.field("currency", pa.string()),
        pa.field("status", pa.string()),
        pa.field("counterparty", pa.string()),
        pa.field("txn_time", pa.timestamp("us")),
        pa.field("settlement_date", pa.date32()),
    ]
)
MANIFEST_SCHEMA = pa.schema(
    [
        pa.field("txn_id", pa.int64()),
        pa.field("defect_class", pa.string()),
        pa.field("side", pa.string()),
        pa.field("detail", pa.string()),
    ]
)


def _write_parquet(table: pa.Table, path: Path) -> None:
    """Write stable parquet bytes for the same Arrow table in one environment."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=3,
        use_dictionary=False,
        write_statistics=False,
        data_page_version="1.0",
        row_group_size=65_536,
    )


def _choose_defect_ids(
    rng: random.Random, count: int, rates: Mapping[str, float]
) -> dict[str, list[int]]:
    requested = {name: int(count * rates[name]) for name in DEFECT_CLASSES}
    total = sum(requested.values())
    if total > count:
        raise ValueError("sum of requested defect rows cannot exceed transaction count")
    population = list(range(1, count + 1))
    rng.shuffle(population)
    cursor = 0
    selected: dict[str, list[int]] = {}
    for name in DEFECT_CLASSES:
        selected[name] = sorted(population[cursor : cursor + requested[name]])
        cursor += requested[name]
    return selected


def generate(
    *,
    seed: int,
    count: int = 100_000,
    rates: Mapping[str, float] | None = None,
    root: str | Path = ".",
) -> dict[str, int]:
    """Generate both ledger views and the isolated ground-truth defect manifest.

    Defects are assigned to disjoint transactions, making each manifest row a
    single auditable expected outcome.  All record ordering and random choices
    are derived from ``seed``.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    effective_rates = dict(DEFAULT_RATES)
    if rates:
        unknown = set(rates) - set(DEFECT_CLASSES)
        if unknown:
            raise ValueError(f"unknown defect classes: {sorted(unknown)}")
        effective_rates.update(rates)
    for name, rate in effective_rates.items():
        if not 0 <= rate <= 1:
            raise ValueError(f"rate for {name} must be between 0 and 1")

    rng = random.Random(seed)
    selected = _choose_defect_ids(rng, count, effective_rates)
    membership = {txn_id: name for name, ids in selected.items() for txn_id in ids}
    root = Path(root)

    switch_rows: list[dict[str, object]] = []
    bank_rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 1, 8, 0, 0)
    currencies = ("INR", "INR", "INR", "USD")

    for txn_id in range(1, count + 1):
        txn_time = start + timedelta(seconds=txn_id * 73 + rng.randrange(60))
        settlement_date = txn_time.date()
        amount_minor = rng.randrange(100, 500_000)
        currency = currencies[rng.randrange(len(currencies))]
        # A checksum-like suffix makes a truncation malformed while retaining
        # the transaction-identifying portion unique across the full dataset.
        utr = f"UTR-{seed:08X}-{txn_id:09d}-CHK{(txn_id * 7919) % 1_000_000:06d}"
        # The first 16 characters are unique per transaction. This lets the
        # constrained fuzzy rule rescue only the intentionally mangled UTR.
        counterparty = f"CP{txn_id:012d}-PAYMENTS"
        switch_row: dict[str, object] = {
            "record_id": f"S-{txn_id:012d}",
            "txn_id": txn_id,
            "utr": utr,
            "amount_minor": amount_minor,
            "currency": currency,
            "status": "SETTLED",
            "counterparty": counterparty,
            "txn_time": txn_time,
            "settlement_date": settlement_date,
        }
        bank_row = dict(switch_row)
        bank_row["record_id"] = f"B-{txn_id:012d}"
        defect = membership.get(txn_id)

        if defect == "MISSING_IN_BANK":
            switch_rows.append(switch_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "BANK", "detail": "bank row removed"}
            )
        elif defect == "MISSING_IN_SWITCH":
            bank_rows.append(bank_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "SWITCH", "detail": "switch row removed"}
            )
        elif defect == "DUPLICATE":
            duplicate_side = "SWITCH" if rng.randrange(2) == 0 else "BANK"
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)
            if duplicate_side == "SWITCH":
                duplicate = dict(switch_row)
                duplicate["record_id"] = f"S-{txn_id:012d}-DUP"
                switch_rows.append(duplicate)
            else:
                duplicate = dict(bank_row)
                duplicate["record_id"] = f"B-{txn_id:012d}-DUP"
                bank_rows.append(duplicate)
            manifest_rows.append(
                {
                    "txn_id": txn_id,
                    "defect_class": defect,
                    "side": duplicate_side,
                    "detail": f"duplicate row on {duplicate_side.lower()} side",
                }
            )
        elif defect == "AMOUNT_MISMATCH":
            bank_row["amount_minor"] = amount_minor + 1
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "BANK", "detail": "bank amount increased by 1"}
            )
        elif defect == "STATUS_MISMATCH":
            switch_row["status"] = "FAILED"
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "SWITCH", "detail": "switch status changed to FAILED"}
            )
        elif defect == "LATE_SETTLEMENT":
            bank_row["settlement_date"] = settlement_date + timedelta(days=1)
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "BANK", "detail": "bank settlement date shifted +1 day"}
            )
        elif defect == "REFERENCE_MANGLED":
            bank_row["utr"] = utr.lower() if txn_id % 2 == 0 else utr[:-4]
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)
            manifest_rows.append(
                {"txn_id": txn_id, "defect_class": defect, "side": "BANK", "detail": "bank UTR case-shifted or truncated"}
            )
        else:
            switch_rows.append(switch_row)
            bank_rows.append(bank_row)

    switch_rows.sort(key=lambda row: str(row["record_id"]))
    bank_rows.sort(key=lambda row: str(row["record_id"]))
    manifest_rows.sort(key=lambda row: (int(row["txn_id"]), str(row["defect_class"])))
    _write_parquet(pa.Table.from_pylist(switch_rows, schema=LEDGER_SCHEMA), root / "data/input/switch_ledger.parquet")
    _write_parquet(pa.Table.from_pylist(bank_rows, schema=LEDGER_SCHEMA), root / "data/input/bank_settlement.parquet")
    _write_parquet(pa.Table.from_pylist(manifest_rows, schema=MANIFEST_SCHEMA), root / "data/oracle/defect_manifest.parquet")
    return {name: len(selected[name]) for name in DEFECT_CLASSES}
