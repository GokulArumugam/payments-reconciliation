-- Retain duplicate flags and keep duplicated keys out of all matching passes.
CREATE OR REPLACE TABLE switch_dedup AS
SELECT *, count(*) OVER (PARTITION BY utr) AS utr_count
FROM switch_normalized;

CREATE OR REPLACE TABLE bank_dedup AS
SELECT *, count(*) OVER (PARTITION BY utr) AS utr_count
FROM bank_normalized;

CREATE OR REPLACE TABLE duplicate_keys AS
SELECT DISTINCT utr FROM switch_dedup WHERE utr_count > 1
UNION
SELECT DISTINCT utr FROM bank_dedup WHERE utr_count > 1;

CREATE OR REPLACE TABLE duplicate_exceptions AS
WITH switch_duplicates AS (
    SELECT utr, min(txn_id) AS txn_id, min(record_id) AS switch_record_id,
           min(settlement_date) AS settlement_date
    FROM switch_dedup
    WHERE utr_count > 1
    GROUP BY utr
), bank_duplicates AS (
    SELECT utr, min(txn_id) AS txn_id, min(record_id) AS bank_record_id,
           min(settlement_date) AS settlement_date
    FROM bank_dedup
    WHERE utr_count > 1
    GROUP BY utr
)
SELECT
    coalesce(s.txn_id, b.txn_id) AS txn_id,
    s.switch_record_id,
    b.bank_record_id,
    s.utr AS switch_utr,
    b.utr AS bank_utr,
    'DUPLICATE' AS exception_class,
    CASE WHEN s.utr IS NOT NULL AND b.utr IS NOT NULL THEN 'BOTH'
         WHEN s.utr IS NOT NULL THEN 'SWITCH' ELSE 'BANK' END AS side,
    coalesce(s.settlement_date, b.settlement_date) AS settlement_date,
    'repeated UTR excluded before matching' AS detail
FROM switch_duplicates s
FULL OUTER JOIN bank_duplicates b USING (utr);
