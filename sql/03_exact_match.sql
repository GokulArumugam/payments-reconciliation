-- Exact UTR matches must also agree on amount and status.  A late date is an
-- auditable exception rather than an invisible successful match.
CREATE OR REPLACE TABLE exact_pairs AS
SELECT
    s.record_id AS switch_record_id,
    b.record_id AS bank_record_id,
    s.txn_id AS switch_txn_id,
    b.txn_id AS bank_txn_id,
    s.utr AS switch_utr,
    b.utr AS bank_utr,
    s.amount_minor AS switch_amount_minor,
    b.amount_minor AS bank_amount_minor,
    s.status AS switch_status,
    b.status AS bank_status,
    s.counterparty AS switch_counterparty,
    b.counterparty AS bank_counterparty,
    s.settlement_date AS switch_settlement_date,
    b.settlement_date AS bank_settlement_date
FROM switch_dedup s
JOIN bank_dedup b ON s.utr = b.utr
WHERE s.utr_count = 1 AND b.utr_count = 1;

CREATE OR REPLACE TABLE exact_matches AS
SELECT
    switch_txn_id, bank_txn_id, switch_txn_id AS txn_id,
    switch_record_id, bank_record_id, switch_utr, bank_utr,
    switch_amount_minor AS amount_minor, switch_status AS status,
    switch_counterparty AS counterparty,
    switch_settlement_date, bank_settlement_date,
    'EXACT_UTR_AMOUNT_STATUS_DATE' AS match_reason,
    CAST(NULL AS VARCHAR) AS detected_class
FROM exact_pairs
WHERE switch_amount_minor = bank_amount_minor
  AND switch_status = bank_status
  AND switch_settlement_date = bank_settlement_date;

CREATE OR REPLACE TABLE exact_exceptions AS
SELECT
    switch_txn_id AS txn_id,
    switch_record_id,
    bank_record_id,
    switch_utr,
    bank_utr,
    CASE
        WHEN switch_amount_minor <> bank_amount_minor THEN 'AMOUNT_MISMATCH'
        WHEN switch_status <> bank_status THEN 'STATUS_MISMATCH'
        ELSE 'LATE_SETTLEMENT'
    END AS exception_class,
    'BOTH' AS side,
    switch_settlement_date AS settlement_date,
    CASE
        WHEN switch_amount_minor <> bank_amount_minor THEN 'same UTR with different amount'
        WHEN switch_status <> bank_status THEN 'same UTR with different status'
        ELSE 'same UTR with different settlement date'
    END AS detail
FROM exact_pairs
WHERE switch_amount_minor <> bank_amount_minor
   OR switch_status <> bank_status
   OR switch_settlement_date <> bank_settlement_date;

CREATE OR REPLACE TABLE switch_exact_residual AS
SELECT s.*
FROM switch_dedup s
WHERE s.utr_count = 1
  AND NOT EXISTS (SELECT 1 FROM duplicate_keys d WHERE d.utr = s.utr)
  AND NOT EXISTS (
      SELECT 1 FROM exact_pairs p WHERE p.switch_record_id = s.record_id
  );

CREATE OR REPLACE TABLE bank_exact_residual AS
SELECT b.*
FROM bank_dedup b
WHERE b.utr_count = 1
  AND NOT EXISTS (SELECT 1 FROM duplicate_keys d WHERE d.utr = b.utr)
  AND NOT EXISTS (
      SELECT 1 FROM exact_pairs p WHERE p.bank_record_id = b.record_id
  );
