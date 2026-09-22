-- RQ1 Provider Distribution Query — window-aligned re-run (2026-07-01 bound)
-- Purpose: Identical to 01_AUDIT_rq1_provider_run.sql in every respect except
--          the upper bound, which is moved from 2026-05-02 (D72) to 2026-07-01
--          to align the RQ1 window with the RQ2 batch window.
--
-- Why this is a separate file, not an edit to 01_AUDIT:
--   01_AUDIT is bounded at 2026-05-02 precisely so it reproduces the figures
--   currently reported in the thesis (2,032,566 events; top 11 = 99.39%; each
--   of the top 11 personally Etherscan-verified by Oscar at that run). Editing
--   its bound in place would destroy that reproducibility before the new
--   numbers have been verified and written up. Once this re-run is accepted
--   and the thesis figures are updated, 01_AUDIT can be retired or superseded
--   explicitly with a documented decision.
--
-- Context: batch 26 (2026 Q2) was executed 2026-06-24 but declares
--   < '2026-07-01', so the RQ2 results were truncated by ~1 week (Session 49
--   finding; confirmed by git: batch results committed 2026-06-24 in 331cc3d,
--   the later 2026-07-20 commit d497f3e being formatting only). Batch 26 is
--   being re-run so RQ2 genuinely covers the full quarter. This query gives
--   RQ1 the same window.
--
-- Both counts are returned deliberately:
--   flash_loan_count    — events, the RQ1 reporting unit
--   unique_transactions — distinct transactions, comparable to RQ2's unit
--   Summing unique_transactions across all rows over-counts slightly: one
--   transaction touching two providers contributes to both rows. Compute the
--   true dataset-level distinct-transaction total with the companion
--   aggregate query below (commented out) rather than by summing this column.
--
-- Methodology alignment: D1, D9, D21 as in 01_AUDIT.
--   D55 — RE-VERIFICATION REQUIRED. The natural break (currently >=8,860
--         events) must be recomputed on this output, and any address newly
--         crossing it must be personally Etherscan-verified before being
--         presented as a provider. The gap-window check
--         (09_gap_window_provider_check.sql) found no unknown address above
--         52 events in 2026-05-02..2026-07-01, so this is expected to be a
--         no-op — but it must be checked, not assumed.
--
-- Export: save output to data/rq1_audit_2026-07-01.csv (do NOT overwrite the
--         2026-05-02 audit export).

SELECT
    LOWER(l.address)                AS pool_address,
    COUNT(*)                        AS flash_loan_count,
    COUNT(DISTINCT l.transaction_hash) AS unique_transactions,
    MIN(l.block_timestamp)          AS first_seen,
    MAX(l.block_timestamp)          AS last_seen
FROM ethereum.decoded.logs l
JOIN ethereum.raw.transactions t ON l.transaction_hash = t.hash
WHERE l.name = 'FlashLoan'
  AND l.block_timestamp >= '2020-01-01'
  AND l.block_timestamp <  '2026-07-01'   -- aligned to RQ2 batch window (was 2026-05-02 under D72)
  AND t.block_timestamp >= '2020-01-01'   -- partition pruning per Session 24 perf optimisations
  AND t.block_timestamp <  '2026-07-01'
GROUP BY LOWER(l.address)
ORDER BY flash_loan_count DESC

-- ---------------------------------------------------------------------------
-- COMPANION AGGREGATE (run separately). Gives the two dataset-level totals:
-- the RQ1 event count, and the deduplicated transaction count that is directly
-- comparable to the RQ2 denominator. This is the query that tests whether
-- "deduplicating the RQ1 events yields the RQ2 transaction count" is true.
--
-- SELECT
--     COUNT(*)                           AS total_flash_loan_events,
--     COUNT(DISTINCT l.transaction_hash) AS total_unique_transactions
-- FROM ethereum.decoded.logs l
-- JOIN ethereum.raw.transactions t ON l.transaction_hash = t.hash
-- WHERE l.name = 'FlashLoan'
--   AND l.block_timestamp >= '2020-01-01'
--   AND l.block_timestamp <  '2026-07-01'
--   AND t.block_timestamp >= '2020-01-01'
--   AND t.block_timestamp <  '2026-07-01'
-- ---------------------------------------------------------------------------
