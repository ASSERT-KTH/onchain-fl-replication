-- RQ4: Flash loan volume against total Ethereum transaction volume, per quarter
-- Window: 2020-01-01 to 2026-07-01 (aligned to the RQ1/RQ2 window, D74)
--
-- Purpose: supervisor feedback (2026-08-27). The six existing RQ4 figures all
--   report use-case SHARES; none reports absolute volume, although
--   5-results.tex states absolute figures in prose. This query provides the
--   absolute flash loan series and a total-Ethereum background series so the
--   two can be plotted together, and so growth in flash loan volume can be
--   read against growth in general chain activity rather than in isolation.
--
-- The supervisor's hypothesis is that flash loan volume spikes when new
--   zero-fee providers arrive (Balancer V2, 2021-10-26; Morpho Blue,
--   2024-01-22) and that the background series will show no matching spike,
--   which would make the spikes flash-loan-specific rather than chain-wide.
--   Query 03 below returns the per-provider series that tests this directly.
--   NOTE: this hypothesis is NOT yet supported by the figures already on hand
--   (batch_results_v3.csv implies 2021 Q4 fell after Balancer V2 launched, and
--   the large rise comes in 2025 Q3-Q4, ~18 months after Morpho Blue). The
--   query is run to test the claim, not to confirm it.
--
-- Scale warning for plotting: flash loans run roughly 0.002%-0.5% of Ethereum
--   transactions, so the two series CANNOT share a linear axis — the flash loan
--   line is flat at zero. Use a log y-axis, or index both series to 100 at
--   2020 Q1. Dual axes are deliberately not recommended: the crossing point is
--   arbitrary and invites a methodological objection.
--
-- Methodology: numerator uses the same base pattern as RQ1
--   (ethereum.decoded.logs name = 'FlashLoan' joined to ethereum.raw.transactions,
--   supervisor decision 2026-03-25) so this series is consistent with the RQ1
--   and RQ2 totals. Counting unit is DISTINCT transaction_hash, matching RQ2's
--   unit, NOT the event count used for the RQ1 headline.
--
-- Export: data/rq4_volume_vs_ethereum.csv

-- ---------------------------------------------------------------------------
-- QUERY 1: Flash loan transactions per quarter
-- ---------------------------------------------------------------------------
SELECT
    DATE_TRUNC('quarter', l.block_timestamp)  AS quarter,
    COUNT(DISTINCT l.transaction_hash)        AS flash_loan_transactions,
    COUNT(*)                                  AS flash_loan_events
FROM ethereum.decoded.logs l
JOIN ethereum.raw.transactions t ON l.transaction_hash = t.hash
WHERE l.name = 'FlashLoan'
  AND l.block_timestamp >= '2020-01-01'
  AND l.block_timestamp <  '2026-07-01'
  AND t.block_timestamp >= '2020-01-01'   -- partition pruning (Session 24)
  AND t.block_timestamp <  '2026-07-01'
GROUP BY 1
ORDER BY 1

-- ---------------------------------------------------------------------------
-- QUERY 2: Total Ethereum transactions per quarter (background series)
--   Run separately. No filter beyond the window — every transaction in every
--   block. This needs no definition of "DeFi" and so carries no coverage
--   caveat, which is why it was chosen over a DeFi-scoped denominator:
--   Allium has no curated all-DeFi table, and assembling one from the dex and
--   lending verticals would have required defining the boundary ourselves.
-- ---------------------------------------------------------------------------
-- SELECT
--     DATE_TRUNC('quarter', block_timestamp) AS quarter,
--     COUNT(*)                               AS total_ethereum_transactions
-- FROM ethereum.raw.transactions
-- WHERE block_timestamp >= '2020-01-01'
--   AND block_timestamp <  '2026-07-01'
-- GROUP BY 1
-- ORDER BY 1

-- ---------------------------------------------------------------------------
-- QUERY 3: Flash loan transactions per quarter, BY PROVIDER
--   Run separately. This is the query that actually tests the supervisor's
--   hypothesis: it shows each provider entering the market and how much volume
--   it brought, rather than asking the reader to infer causation from a single
--   aggregate line and two vertical markers.
--   Provider CASE is copied verbatim from the RQ2 batch files (11 verified
--   providers, D55/D74). 'Unknown' is retained rather than filtered so the
--   rows still sum to the Query 1 totals.
-- ---------------------------------------------------------------------------
-- SELECT
--     DATE_TRUNC('quarter', l.block_timestamp) AS quarter,
--     CASE
--         WHEN LOWER(l.address) = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb' THEN 'Morpho Blue'
--         WHEN LOWER(l.address) = '0xba12222222228d8ba445958a75a0704d566bf2c8' THEN 'Balancer V2'
--         WHEN LOWER(l.address) = '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2' THEN 'Aave V3 (Core Market)'
--         WHEN LOWER(l.address) = '0x26de7861e213a5351f6ed767d00e0839930e9ee1' THEN 'Curve crvUSD (FlashLender)'
--         WHEN LOWER(l.address) = '0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9' THEN 'Aave V2'
--         WHEN LOWER(l.address) = '0xc13e21b648a5ee794902342038ff3adab66be987' THEN 'Spark Lend'
--         WHEN LOWER(l.address) = '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa' THEN 'MakerDAO/Sky (DssFlash)'
--         WHEN LOWER(l.address) = '0x398ec7346dcd622edc5ae82352f02be94c62d119' THEN 'Aave V1'
--         WHEN LOWER(l.address) = '0xdbfd76af2157dc15ee4e57f3f942bb45ba84af24' THEN 'BendDAO boundBAYC (NFT flash loan)'
--         WHEN LOWER(l.address) = '0x69f37e419bd1457d2a25ed3f5d418169caae8d1f' THEN 'BendDAO boundMAYC (NFT flash loan)'
--         WHEN LOWER(l.address) = '0x1eb4cf3a948e7d72a198fe073ccb8c7a948cd853' THEN 'MakerDAO (DssFlash v1)'
--         ELSE 'Unknown'
--     END                                      AS provider,
--     COUNT(DISTINCT l.transaction_hash)       AS flash_loan_transactions
-- FROM ethereum.decoded.logs l
-- JOIN ethereum.raw.transactions t ON l.transaction_hash = t.hash
-- WHERE l.name = 'FlashLoan'
--   AND l.block_timestamp >= '2020-01-01'
--   AND l.block_timestamp <  '2026-07-01'
--   AND t.block_timestamp >= '2020-01-01'
--   AND t.block_timestamp <  '2026-07-01'
-- GROUP BY 1, 2
-- ORDER BY 1, 3 DESC
