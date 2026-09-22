-- RQ3: benign comparison sample (stratified by quarter)
--
-- Draws the benign group for the RQ3 structural comparison: up to 38 FlashLoan
-- transactions per quarter across the 26 quarters of 2020 Q1 - 2026 Q2.
--
-- Output: data/rq3_benign_sample_stratified.csv (transaction_hash, block_timestamp, quarter)
--
-- Realized n = 874, not the 988 the cap implies. The per-quarter cap is a ceiling,
-- not a quota: flash loan activity is sparse in the earliest quarters, so seven
-- quarters held fewer than 38 candidates and were taken in full (2020 Q1=7, Q2=4,
-- Q3=12, Q4=30; 2021 Q1=37, Q4=26; 2022 Q1=36). 874 is the realized n of the
-- a-priori rule rather than a figure chosen after the fact.
--
-- Deterministic: both the pre-filter bucket and the ordering are HASH-based, so
-- re-running returns the same rows. The % 200 pre-filter keeps roughly 0.5% of the
-- population so the window function sorts a small pool rather than ~2M rows; if a
-- quarter comes back short of its cap, lower the modulus.
--
-- No exclusions at the sampling step. Known-attack hashes and NFT-operation
-- transactions are NOT filtered out here: benign is defined as the general
-- FlashLoan population, and anything unusual that lands in the sample is
-- characterised after profiling rather than removed up front, which avoids making
-- the sample depend on the same registries the classification engine uses.
-- Expected attack contamination is negligible (30 known attacks carrying a
-- FlashLoan event in ~2.2M transactions).
--
-- Joins raw.transactions so the sample holds only external, EOA-initiated
-- transactions, matching the base-table pattern used throughout the thesis.

WITH flash_loans AS (
    SELECT DISTINCT
        l.transaction_hash,
        l.block_timestamp,
        DATE_TRUNC('quarter', l.block_timestamp) AS quarter
    FROM ethereum.decoded.logs AS l
    JOIN ethereum.raw.transactions AS t
      ON t.hash = l.transaction_hash
     AND t.block_timestamp = l.block_timestamp
    WHERE l.name = 'FlashLoan'
      AND l.block_timestamp >= '2020-01-01'
      AND l.block_timestamp <  '2026-07-01'
      -- Deterministic pre-filter: shrink the pool before the per-quarter sort.
      AND ABS(HASH(l.transaction_hash)) % 200 = 0
)
SELECT
    transaction_hash,
    block_timestamp,
    quarter
FROM flash_loans
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY quarter
    ORDER BY HASH(transaction_hash)
) <= 38
ORDER BY block_timestamp
