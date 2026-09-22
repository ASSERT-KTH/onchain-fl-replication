-- =============================================================================
-- RQ2: Use Case Classification Engine v3 (multilabel, hybrid Allium + trace)
-- =============================================================================
-- The classification engine behind every RQ2 and RQ4 figure in the thesis.
-- Layers, each firing independently:
--   L0  known-attack transaction hashes
--   L1  anchor contracts        (data/ground_truth/anchor_contracts.csv)
--   L2  function selectors      (data/ground_truth/function_signatures.csv)
--   L3a lending protocol calls  (data/ground_truth/lending_protocol_contracts.csv)
--   L3b DEX router / pool calls (data/ground_truth/dex_router_contracts.csv,
--                                data/ground_truth/dex_trade_functions.csv)
--   L4  Allium enrichment tables (dex.trades, lending.*)
--
-- MULTILABEL: a transaction can match several use cases; each fires on its own,
-- so pct_of_transactions sums to >100% by design. This is intended, not a bug.
--
-- -----------------------------------------------------------------------------
-- RUNNING IT
-- -----------------------------------------------------------------------------
-- The engine is date-scoped in 9 CTEs (18 literals: a >= and a < in each).
-- Running the full 2020-2026 population in one pass exceeds Allium's query
-- timeout, so the reported results were produced one quarter at a time and the
-- 26 outputs appended to data/batch_results_v3.csv.
--
-- Per quarter: replace {{START}} and {{END}} with one row of the table below.
--
-- Full population in one pass: delete the 9 `< '{{END}}'` lines and set every
-- {{START}} to 2020-01-01. Only do this if the query is given room to complete.
--
-- -----------------------------------------------------------------------------
-- QUARTERS (26, contiguous, 2020-01-01 -> 2026-07-01; the D74 window)
-- -----------------------------------------------------------------------------
--   Quarter   {{START}}     {{END}}          Quarter   {{START}}     {{END}}
--   2020 Q1   2020-01-01    2020-04-01       2023 Q3   2023-07-01    2023-10-01
--   2020 Q2   2020-04-01    2020-07-01       2023 Q4   2023-10-01    2024-01-01
--   2020 Q3   2020-07-01    2020-10-01       2024 Q1   2024-01-01    2024-04-01
--   2020 Q4   2020-10-01    2021-01-01       2024 Q2   2024-04-01    2024-07-01
--   2021 Q1   2021-01-01    2021-04-01       2024 Q3   2024-07-01    2024-10-01
--   2021 Q2   2021-04-01    2021-07-01       2024 Q4   2024-10-01    2025-01-01
--   2021 Q3   2021-07-01    2021-10-01       2025 Q1   2025-01-01    2025-04-01
--   2021 Q4   2021-10-01    2022-01-01       2025 Q2   2025-04-01    2025-07-01
--   2022 Q1   2022-01-01    2022-04-01       2025 Q3   2025-07-01    2025-10-01
--   2022 Q2   2022-04-01    2022-07-01       2025 Q4   2025-10-01    2026-01-01
--   2022 Q3   2022-07-01    2022-10-01       2026 Q1   2026-01-01    2026-04-01
--   2022 Q4   2022-10-01    2023-01-01       2026 Q2   2026-04-01    2026-07-01
--   2023 Q1   2023-01-01    2023-04-01
--   2023 Q2   2023-04-01    2023-07-01
-- =============================================================================


WITH flash_loans AS (
    SELECT
        l.transaction_hash,
        t.from_address                  AS eoa_address,
        l.address                       AS pool_address,
        l.block_timestamp,
        CASE
            WHEN LOWER(l.address) = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb' THEN 'Morpho Blue'
            WHEN LOWER(l.address) = '0xba12222222228d8ba445958a75a0704d566bf2c8' THEN 'Balancer V2'
            WHEN LOWER(l.address) = '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2' THEN 'Aave V3 (Core Market)'
            WHEN LOWER(l.address) = '0x26de7861e213a5351f6ed767d00e0839930e9ee1' THEN 'Curve crvUSD (FlashLender)'
            WHEN LOWER(l.address) = '0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9' THEN 'Aave V2'
            WHEN LOWER(l.address) = '0xc13e21b648a5ee794902342038ff3adab66be987' THEN 'Spark Lend'
            WHEN LOWER(l.address) = '0x60744434d6339a6b27d73d9eda62b6f66a0a04fa' THEN 'MakerDAO/Sky (DssFlash)'
            WHEN LOWER(l.address) = '0x398ec7346dcd622edc5ae82352f02be94c62d119' THEN 'Aave V1'
            WHEN LOWER(l.address) = '0xdbfd76af2157dc15ee4e57f3f942bb45ba84af24' THEN 'BendDAO boundBAYC (NFT flash loan)'
            WHEN LOWER(l.address) = '0x69f37e419bd1457d2a25ed3f5d418169caae8d1f' THEN 'BendDAO boundMAYC (NFT flash loan)'
            WHEN LOWER(l.address) = '0x1eb4cf3a948e7d72a198fe073ccb8c7a948cd853' THEN 'MakerDAO (DssFlash v1)'
            ELSE 'Unknown'
        END AS provider,
        COALESCE(l.params:asset::STRING, l.params:token::STRING) AS token_address,
        l.params:amount::STRING AS amount
    FROM ethereum.decoded.logs l
    INNER JOIN ethereum.raw.transactions t
        ON l.transaction_hash = t.hash
        AND t.block_timestamp >= '{{START}}'
        AND t.block_timestamp < '{{END}}'
    WHERE l.name = 'FlashLoan'
      AND l.block_timestamp >= '{{START}}'
      AND l.block_timestamp < '{{END}}'
),

trace_signals AS (
    SELECT
        fl.transaction_hash,
        -- collateral_swap anchors: 11 addresses
        MAX(CASE WHEN LOWER(tr.to_address) IN (
            '0x80aca0c645fedabaa20fd2bf0daf57885a309fe6',
            '0x498c5431eb517101582988fbb36431ddaac8f4b1',
            '0x135896de8421be2ec868e0b811006171d9df802a',
            '0x02e7b8511831b1b02d9018215a0f8f500ea5c6b3',
            '0x35bb522b102326ea3f1141661df4626c87000e3e',
            '0xadc0a53095a0af87f3aa29fe0715b5c28016364e',
            '0x66e1abdb06e7363a618d65a910c540dfed23754f',
            '0xd0887aa7febc8962c622493646195e7c76d94fce',
            '0x872fbcb1b582e8cd0d0dd4327fbfa0b4c2730995',
            '0x1809f186d680f239420b56948c58f8dbbcdf1e18',
            '0xa859dff8bcee9c6daaef5d0eccb25219da4b62b4'
        ) THEN 1 ELSE 0 END) AS has_cs_anchor,

        -- debt_swap anchors: 2 addresses
        MAX(CASE WHEN LOWER(tr.to_address) IN (
            '0xd7852e139a7097e119623de0751ae53a61efb442',
            '0xaf5c88245cd02ff3df332ef1e1ffd5bc5d1d87cd'
        ) THEN 1 ELSE 0 END) AS has_ds_anchor,

        -- liquidation functions (name for unambiguous, selector for overloaded 'liquidate')
        MAX(CASE WHEN tr.name IN ('liquidationCall', 'liquidate_extended', 'bark', 'bite')
                  OR tr.selector IN (
                      '0xd8eabcb8',  -- Morpho Blue: liquidate((address,address,address,address,uint256),address,uint256,uint256,bytes)
                      '0xbcbaf487',  -- Curve crvUSD: liquidate(address,uint256)
                      '0x3ecdb828',  -- Curve crvUSD: liquidate(address,uint256,bool)
                      '0x0710285c'   -- BendDAO Core LendPool: liquidate(address,uint256,uint256)
                  )
             THEN 1 ELSE 0 END) AS has_liquidation_function

    FROM flash_loans fl
    INNER JOIN ethereum.decoded.traces tr
        ON fl.transaction_hash = tr.transaction_hash
        AND tr.block_timestamp >= '{{START}}'
        AND tr.block_timestamp < '{{END}}'
    GROUP BY fl.transaction_hash
),

allium_liquidations AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.lending.liquidations liq
        ON liq.transaction_hash = fl.transaction_hash
        AND liq.block_timestamp >= '{{START}}'
        AND liq.block_timestamp < '{{END}}'
),

allium_withdrawals AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.lending.withdrawals w
        ON w.transaction_hash = fl.transaction_hash
        AND w.block_timestamp >= '{{START}}'
        AND w.block_timestamp < '{{END}}'
),

allium_deposits AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.lending.deposits d
        ON d.transaction_hash = fl.transaction_hash
        AND d.block_timestamp >= '{{START}}'
        AND d.block_timestamp < '{{END}}'
),

allium_repayments AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.lending.repayments r
        ON r.transaction_hash = fl.transaction_hash
        AND r.block_timestamp >= '{{START}}'
        AND r.block_timestamp < '{{END}}'
),

allium_loans AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.lending.loans lo
        ON lo.transaction_hash = fl.transaction_hash
        AND lo.block_timestamp >= '{{START}}'
        AND lo.block_timestamp < '{{END}}'
),

allium_dex AS (
    SELECT DISTINCT fl.transaction_hash
    FROM flash_loans fl
    INNER JOIN ethereum.dex.trades dex
        ON dex.transaction_hash = fl.transaction_hash
        AND dex.block_timestamp >= '{{START}}'
        AND dex.block_timestamp < '{{END}}'
),

allium_cs AS (
    SELECT transaction_hash
    FROM allium_withdrawals
    WHERE transaction_hash IN (SELECT transaction_hash FROM allium_deposits)
),

allium_ds AS (
    SELECT transaction_hash
    FROM allium_repayments
    WHERE transaction_hash IN (SELECT transaction_hash FROM allium_loans)
),

classified AS (
    SELECT
        fl.transaction_hash,
        fl.pool_address,
        fl.block_timestamp,
        fl.provider,
        CASE WHEN LOWER(fl.pool_address) IN (
            '0xdbfd76af2157dc15ee4e57f3f942bb45ba84af24',
            '0x69f37e419bd1457d2a25ed3f5d418169caae8d1f'
        ) THEN 1 ELSE 0 END AS is_nft,
        COALESCE(ts.has_cs_anchor, 0)          AS has_cs_anchor,
        COALESCE(ts.has_ds_anchor, 0)          AS has_ds_anchor,
        COALESCE(ts.has_liquidation_function, 0) AS has_liquidation_function,
        CASE WHEN al.transaction_hash IS NOT NULL THEN 1 ELSE 0 END AS has_allium_liquidation,
        CASE WHEN acs.transaction_hash IS NOT NULL THEN 1 ELSE 0 END AS has_allium_cs,
        CASE WHEN ads.transaction_hash IS NOT NULL THEN 1 ELSE 0 END AS has_allium_ds,
        CASE WHEN adx.transaction_hash IS NOT NULL THEN 1 ELSE 0 END AS has_dex_trade
    FROM flash_loans fl
    LEFT JOIN trace_signals ts  ON fl.transaction_hash = ts.transaction_hash
    LEFT JOIN allium_liquidations al  ON fl.transaction_hash = al.transaction_hash
    LEFT JOIN allium_cs acs     ON fl.transaction_hash = acs.transaction_hash
    LEFT JOIN allium_ds ads     ON fl.transaction_hash = ads.transaction_hash
    LEFT JOIN allium_dex adx    ON fl.transaction_hash = adx.transaction_hash
),

labeled AS (
    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'nft_operations' AS use_case, 'pre_filter_benddao' AS classification_method
    FROM classified WHERE is_nft = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'collateral_swap', 'layer1_anchor_contract'
    FROM classified WHERE has_cs_anchor = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'debt_swap', 'layer1_anchor_contract'
    FROM classified WHERE has_ds_anchor = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'liquidation', 'layer2_trace_function'
    FROM classified WHERE has_liquidation_function = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'liquidation', 'layer2_allium_liquidation'
    FROM classified WHERE has_allium_liquidation = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'collateral_swap', 'layer3_allium_lending'
    FROM classified WHERE has_allium_cs = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'debt_swap', 'layer3_allium_lending'
    FROM classified WHERE has_allium_ds = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'arbitrage', 'layer4_dex_interaction'
    FROM classified WHERE has_dex_trade = 1

    UNION ALL

    SELECT transaction_hash, pool_address, block_timestamp, provider,
           'unknown', 'unclassified'
    FROM classified
    WHERE is_nft = 0
      AND has_cs_anchor = 0
      AND has_ds_anchor = 0
      AND has_liquidation_function = 0
      AND has_allium_liquidation = 0
      AND has_allium_cs = 0
      AND has_allium_ds = 0
      AND has_dex_trade = 0
),

per_layer AS (
    SELECT
        use_case,
        classification_method,
        COUNT(*) AS flash_loan_events,
        COUNT(DISTINCT transaction_hash) AS unique_transactions
    FROM labeled
    GROUP BY use_case, classification_method
),

per_use_case AS (
    SELECT
        use_case,
        COUNT(DISTINCT transaction_hash) AS unique_transactions
    FROM labeled
    GROUP BY use_case
),

totals AS (
    SELECT COUNT(DISTINCT transaction_hash) AS total_transactions
    FROM classified
)

-- OUTPUT 1: Per-layer breakdown (for validation / methodology)
SELECT
    'per_layer' AS output_type,
    p.use_case,
    p.classification_method,
    p.flash_loan_events,
    p.unique_transactions,
    ROUND(100.0 * p.flash_loan_events / SUM(p.flash_loan_events) OVER (), 2) AS pct_of_events,
    ROUND(100.0 * p.unique_transactions / t.total_transactions, 2) AS pct_of_transactions
FROM per_layer p
CROSS JOIN totals t

UNION ALL

-- OUTPUT 2: Per-use-case summary (deduplicated within each use_case bucket)
SELECT
    'per_use_case' AS output_type,
    u.use_case,
    NULL AS classification_method,
    NULL AS flash_loan_events,
    u.unique_transactions,
    NULL AS pct_of_events,
    ROUND(100.0 * u.unique_transactions / t.total_transactions, 2) AS pct_of_transactions
FROM per_use_case u
CROSS JOIN totals t

ORDER BY output_type, pct_of_transactions DESC NULLS LAST
