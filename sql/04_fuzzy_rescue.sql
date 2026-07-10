-- Fuzzy rescue is deliberately narrow and fully deterministic.  More than one
-- candidate is an exception: it is never silently resolved by the tie-break.
CREATE OR REPLACE TABLE fuzzy_candidates AS
SELECT
    s.record_id AS switch_record_id,
    b.record_id AS bank_record_id,
    s.txn_id AS switch_txn_id,
    b.txn_id AS bank_txn_id,
    s.utr AS switch_utr,
    b.utr AS bank_utr,
    s.amount_minor,
    s.status,
    s.counterparty,
    s.settlement_date AS switch_settlement_date,
    b.settlement_date AS bank_settlement_date,
    abs(b.settlement_date - s.settlement_date) AS date_distance
FROM switch_exact_residual s
JOIN bank_exact_residual b
  ON s.amount_minor = b.amount_minor
 AND abs(b.settlement_date - s.settlement_date) <= 1
 AND substring(s.counterparty, 1, 16) = substring(b.counterparty, 1, 16);

CREATE OR REPLACE TABLE fuzzy_switch_counts AS
SELECT switch_record_id, count(*) AS candidate_count
FROM fuzzy_candidates
GROUP BY switch_record_id;

-- This stable ordering is retained for audit/review. A candidate set with more
-- than one row is still surfaced as AMBIGUOUS rather than auto-selected.
CREATE OR REPLACE TABLE fuzzy_ranked AS
SELECT *,
       row_number() OVER (
           PARTITION BY switch_record_id
           ORDER BY date_distance, bank_record_id
       ) AS candidate_rank
FROM fuzzy_candidates;

CREATE OR REPLACE TABLE fuzzy_bank_counts AS
SELECT bank_record_id, count(*) AS candidate_count
FROM fuzzy_candidates
GROUP BY bank_record_id;

CREATE OR REPLACE TABLE fuzzy_ambiguous_exceptions AS
SELECT DISTINCT
    c.switch_txn_id AS txn_id,
    c.switch_record_id,
    c.bank_record_id,
    c.switch_utr,
    c.bank_utr,
    'AMBIGUOUS' AS exception_class,
    'BOTH' AS side,
    c.switch_settlement_date AS settlement_date,
    'multiple constrained fuzzy candidates; no automatic match' AS detail
FROM fuzzy_ranked c
JOIN fuzzy_switch_counts sc USING (switch_record_id)
JOIN fuzzy_bank_counts bc USING (bank_record_id)
WHERE (sc.candidate_count > 1 OR bc.candidate_count > 1)
  AND c.candidate_rank = 1;

CREATE OR REPLACE TABLE fuzzy_matches AS
SELECT
    c.switch_txn_id,
    c.bank_txn_id,
    c.switch_txn_id AS txn_id,
    c.switch_record_id,
    c.bank_record_id,
    c.switch_utr,
    c.bank_utr,
    c.amount_minor,
    c.status,
    c.counterparty,
    c.switch_settlement_date,
    c.bank_settlement_date,
    'FUZZY_AMOUNT_DATE_COUNTERPARTY_PREFIX; closest-date-then-lowest-id' AS match_reason,
    'REFERENCE_MANGLED' AS detected_class
FROM fuzzy_candidates c
JOIN fuzzy_switch_counts sc USING (switch_record_id)
JOIN fuzzy_bank_counts bc USING (bank_record_id)
WHERE sc.candidate_count = 1 AND bc.candidate_count = 1;

CREATE OR REPLACE TABLE fuzzy_consumed_switch AS
SELECT switch_record_id FROM fuzzy_matches
UNION
SELECT switch_record_id FROM fuzzy_ambiguous_exceptions;

CREATE OR REPLACE TABLE fuzzy_consumed_bank AS
SELECT bank_record_id FROM fuzzy_matches
UNION
SELECT c.bank_record_id
FROM fuzzy_candidates c
JOIN fuzzy_switch_counts sc USING (switch_record_id)
JOIN fuzzy_bank_counts bc USING (bank_record_id)
WHERE sc.candidate_count > 1 OR bc.candidate_count > 1;

CREATE OR REPLACE TABLE switch_post_fuzzy_residual AS
SELECT s.*
FROM switch_exact_residual s
WHERE NOT EXISTS (
    SELECT 1 FROM fuzzy_consumed_switch c WHERE c.switch_record_id = s.record_id
);

CREATE OR REPLACE TABLE bank_post_fuzzy_residual AS
SELECT b.*
FROM bank_exact_residual b
WHERE NOT EXISTS (
    SELECT 1 FROM fuzzy_consumed_bank c WHERE c.bank_record_id = b.record_id
);
