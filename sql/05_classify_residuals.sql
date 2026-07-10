-- Classify the remaining rows, then emit the two reconciler artifacts.
CREATE OR REPLACE TABLE residual_exceptions AS
SELECT
    txn_id,
    record_id AS switch_record_id,
    CAST(NULL AS VARCHAR) AS bank_record_id,
    utr AS switch_utr,
    CAST(NULL AS VARCHAR) AS bank_utr,
    'MISSING_IN_BANK' AS exception_class,
    'BANK' AS side,
    settlement_date,
    'switch transaction has no bank counterpart after all passes' AS detail
FROM switch_post_fuzzy_residual
UNION ALL
SELECT
    txn_id,
    CAST(NULL AS VARCHAR) AS switch_record_id,
    record_id AS bank_record_id,
    CAST(NULL AS VARCHAR) AS switch_utr,
    utr AS bank_utr,
    'MISSING_IN_SWITCH' AS exception_class,
    'SWITCH' AS side,
    settlement_date,
    'bank settlement has no switch counterpart after all passes' AS detail
FROM bank_post_fuzzy_residual;

CREATE OR REPLACE TABLE exceptions_raw AS
SELECT * FROM duplicate_exceptions
UNION ALL
SELECT * FROM exact_exceptions
UNION ALL
SELECT * FROM fuzzy_ambiguous_exceptions
UNION ALL
SELECT * FROM residual_exceptions;

CREATE OR REPLACE TABLE exceptions_final AS
SELECT
    txn_id,
    switch_record_id,
    bank_record_id,
    switch_utr,
    bank_utr,
    exception_class,
    exception_class AS detected_class,
    side,
    CASE
        WHEN exception_class IN ('MISSING_IN_BANK', 'MISSING_IN_SWITCH') THEN 'CRITICAL'
        WHEN exception_class IN ('AMOUNT_MISMATCH', 'STATUS_MISMATCH', 'DUPLICATE', 'AMBIGUOUS') THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity,
    CASE
        WHEN (current_date - settlement_date) <= 1 THEN '0-1d'
        WHEN (current_date - settlement_date) <= 7 THEN '2-7d'
        ELSE '8d+'
    END AS aging_bucket,
    settlement_date,
    detail
FROM exceptions_raw;

CREATE OR REPLACE TABLE matches_final AS
SELECT * FROM exact_matches
UNION ALL
SELECT * FROM fuzzy_matches;

COPY matches_final TO '{{matches_path}}' (FORMAT PARQUET, COMPRESSION ZSTD);
COPY exceptions_final TO '{{exceptions_path}}' (FORMAT PARQUET, COMPRESSION ZSTD);
