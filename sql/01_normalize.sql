-- Normalize both source views into a single, explicit schema.
CREATE OR REPLACE TABLE switch_normalized AS
SELECT
    CAST(record_id AS VARCHAR) AS record_id,
    CAST(txn_id AS BIGINT) AS txn_id,
    CAST(utr AS VARCHAR) AS utr,
    CAST(amount_minor AS BIGINT) AS amount_minor,
    CAST(currency AS VARCHAR) AS currency,
    CAST(status AS VARCHAR) AS status,
    CAST(counterparty AS VARCHAR) AS counterparty,
    CAST(txn_time AS TIMESTAMP) AS txn_time,
    CAST(settlement_date AS DATE) AS settlement_date
FROM read_parquet('{{switch_path}}');

CREATE OR REPLACE TABLE bank_normalized AS
SELECT
    CAST(record_id AS VARCHAR) AS record_id,
    CAST(txn_id AS BIGINT) AS txn_id,
    CAST(utr AS VARCHAR) AS utr,
    CAST(amount_minor AS BIGINT) AS amount_minor,
    CAST(currency AS VARCHAR) AS currency,
    CAST(status AS VARCHAR) AS status,
    CAST(counterparty AS VARCHAR) AS counterparty,
    CAST(txn_time AS TIMESTAMP) AS txn_time,
    CAST(settlement_date AS DATE) AS settlement_date
FROM read_parquet('{{bank_path}}');
