# Flash Loans on Ethereum — Thesis Data and Queries

Supporting material for the master's thesis *"History of Flash Loans: A Data-Driven
Analysis of Legitimate Usage and Attack Patterns"* (Oscar Reina Gustafsson, KTH Royal
Institute of Technology).

This repository holds the SQL queries, hand-curated ground truth, and incident-collection
scripts behind the results reported in the thesis. It is a **reference artifact**: it
documents how the numbers were produced and lets a reader inspect the queries and the
ground truth directly. It is not a one-command reproduction pipeline — see
[Scope and limitations](#scope-and-limitations).

## Data source

On-chain data comes from [Allium](https://www.allium.so) Explorer, a commercial platform
that indexes Ethereum and exposes ABI-decoded transactions, events, and traces. The two
base tables are `ethereum.raw.transactions` and `ethereum.decoded.logs`; the classification
engine additionally reads Allium's `lending.*` and `dex.trades` enrichment tables.

Running the queries requires an Allium account. The raw transaction data is not
redistributed here — only the queries and the aggregate results they produced.

Study window: **2020-01-01 to 2026-07-01**.

## Layout

```
sql/
  rq1_identification/
    10_rq1_provider_run_2026-07-01.sql      provider distribution (RQ1)
  rq2_classification/
    classification_engine.sql               use-case classification engine (RQ2)
  rq3_structural/
    benign_sample_stratified.sql            benign comparison sample (RQ3)
  rq4_temporal/
    01_flash_loans_vs_ethereum_quarterly.sql  quarterly volume vs. Ethereum (RQ4)

src/extraction/                             attack-incident collection pipeline

analysis/
  rq3_structural_comparison.py              trace profiles -> features, medians (RQ3)
  rq3_classifier.py                         random forest separability (RQ3)
  rq3_per_attack_outcomes.py                per-attack CV outcome table (RQ3)

data/
  ground_truth/                             hand-curated registries and incidents
  defillama/                                TVL snapshot for background section
  batch_results_v3.csv                      classification output (RQ2, RQ4)
  rq1_audit_2026-07-01.csv                  provider distribution output (RQ1)
  rq4_volume_vs_ethereum.csv                quarterly volume series (RQ4)
  rq3_benign_sample_stratified.csv          benign comparison sample (RQ3)
```

## The queries

### RQ1 — identifying providers

`sql/rq1_identification/10_rq1_provider_run_2026-07-01.sql` ranks every contract emitting a
`FlashLoan` event over the study window. Output: `data/rq1_audit_2026-07-01.csv` (78
addresses).

Summing `flash_loan_count` gives the **2,359,834 events** reported in the thesis; the
eleven named providers account for **99.47%** of them.

> Note: summing the per-pool `unique_transactions` column gives 2,228,305, which is *not*
> the 2,195,038 transaction figure in the thesis. A transaction touching two pools is
> counted once per pool here. The thesis figure is a `COUNT(DISTINCT transaction_hash)`
> over the whole population.

### RQ2 — classifying use cases

`sql/rq2_classification/classification_engine.sql` is the multilabel classification engine.
A transaction may match several use cases; each fires independently, so shares sum to more
than 100% by design.

| Layer | Signal | Source |
|-------|--------|--------|
| L1 | adapter contract called in traces | `data/ground_truth/anchor_contracts.csv` |
| L2 | liquidation function called in traces | `data/ground_truth/function_signatures.csv` |
| L3 | lending position change | Allium `lending.*` tables |
| L4 | DEX swap | Allium `dex.trades` |

L1 and L2 match against the hand-verified registries in `data/ground_truth/`, inlined in
the query as address and selector literals. L3 detects a collateral swap as a
`withdrawals` + `deposits` pair on different assets in one transaction, and a debt swap as
a `repayments` + `loans` pair. L4 labels any transaction with at least one `dex.trades` row
as arbitrage.

**Running it.** The engine is date-scoped in 9 CTEs (18 literals). Running the full
population in one pass exceeds Allium's query timeout, so the reported results were
produced one quarter at a time: substitute `{{START}}` and `{{END}}` with one row from the
26-quarter table in the file header, run, and append the output. The 26 quarterly outputs
are `data/batch_results_v3.csv`.

### RQ4 — volume over time

`sql/rq4_temporal/01_flash_loans_vs_ethereum_quarterly.sql` reports flash loan
transactions per quarter against total Ethereum transactions. Output:
`data/rq4_volume_vs_ethereum.csv` (26 quarters, with indexed columns for plotting).

## Ground truth

Everything in `data/ground_truth/` was assembled and verified by hand against Etherscan,
protocol documentation, and incident post-mortems. These files are not derived from Allium.

| File | Rows | Contents |
|------|------|----------|
| `anchor_contracts.csv` | 13 | L1 adapter contracts. Each row records the Etherscan label, the verified contract source name, and the code family it belongs to. |
| `function_signatures.csv` | 13 | L2 function selectors. Each row cites the verified implementation contract the signature was read from, with notes on why the function unambiguously indicates its use case. |
| `flash_loan_attacks_v2.csv` | 67 | Flash loan attack incidents, deduplicated across three sources. `has_flashloan_event` records whether the transaction emits a standard `FlashLoan` event: 30 `yes`, 24 `no`, 8 `unknown` (no hash recoverable), 4 `n/a` (not Ethereum), 1 `non_standard`. The 30 `yes` rows are the attack sample used in RQ3. The `non_standard` row is DODO (2021-03-08), whose provider emits a protocol-specific `DODOFlashLoan` event: the incident is real and the transaction hash is correct, but it is invisible to the RQ1 identification filter and so cannot enter a sample drawn from that population. |
| `lookup_results.csv` | 57 | The manual verification pass behind the incident hashes, one row per incident, with the reasoning and the post-mortem consulted. |
| `defillama_flashloan_attacks.csv` | 40 | Pinned DeFiLlama export, input to the collection pipeline. |

`data/rq3_benign_sample_stratified.csv` holds the 874-transaction benign comparison group
for RQ3, drawn by `sql/rq3_structural/benign_sample_stratified.sql`: up to 38 transactions per
quarter across the 26 quarters, deterministic in both its pre-filter and its ordering, so
re-running returns the same rows.

The realized n is 874 rather than the 988 the cap implies. The per-quarter cap is a ceiling,
not a quota, and seven early quarters held fewer than 38 candidates and were taken in full
(2020 Q1=7, Q2=4, Q3=12, Q4=30; 2021 Q1=37, Q4=26; 2022 Q1=36). Nothing is excluded at the
sampling step: known attacks and NFT-operation transactions are not filtered out, since benign
is defined as the general flash loan population and anything unusual is characterised after
profiling rather than removed up front.

`data/defillama/` is a TVL snapshot pinned to 2026-07-01, used for the market-structure
figures in the background chapter. See the README in that directory for the caveats —
in particular, TVL is not flash loan liquidity.

## RQ3 — attacks against benign usage

`analysis/` holds the three scripts behind the RQ3 structural comparison. They run in
sequence, each reading what the previous one wrote:

| Script | Reads | Writes |
|--------|-------|--------|
| `rq3_structural_comparison.py` | `data/ground_truth/flash_loan_attacks_v2.csv`, `data/rq3_benign_sample_stratified.csv` | `profiles_flat.csv`, `summary_stats.json` |
| `rq3_classifier.py` | `profiles_flat.csv` | `classifier/metrics.json`, `classifier/feature_importance.json` |
| `rq3_per_attack_outcomes.py` | `profiles_flat.csv` | `classifier/per_attack_outcomes.csv` |

The sample is **30 attack transactions against 874 benign** (904 rows). Six features are
read from each transaction's call trace: `total_calls`, `max_depth`, `unique_contract_count`,
`unique_selector_count`, `gas_used` and `failed_subcalls`.

**The first script needs an archive node.** It profiles every transaction hash by shelling out
to `tx-profiler` ([sofiabobadilla/tx_profiler](https://github.com/sofiabobadilla/tx_profiler)),
which walks the full internal call trace. That tool is not part of this repository and the
resulting `profiles_flat.csv` is not redistributed, so the pipeline cannot be run end to end
from here. The two classifier scripts are deterministic given
that file: a fixed seed, five stratified folds, scikit-learn defaults with balanced class
weights, and no hyperparameter tuning.

Two things to know before reading the numbers. Removing or adding one attack **re-stratifies all
five folds**, so per-fold and per-attack results change throughout rather than only for the row
that moved — the per-attack table must be regenerated, never patched. And permutation importance
separates `gas_used` clearly from the rest but leaves the middle features close enough together
that their relative order is not meaningful; the thesis says so where it reports them.

## Incident collection

`src/extraction/` assembles the attack incident list from three sources:

```
python -m src.extraction.run_extraction
```

Steps: collect from SlowMist Hacked, DeFiLlama, and DeFiHackLabs; merge and deduplicate on
(protocol, month); recover transaction hashes from Etherscan URLs in post-mortems and from
DeFiHackLabs proof-of-concept files; write `flash_loan_attacks_v2.csv`.

Requires `requests` and `beautifulsoup4`, plus a local clone for the DeFiHackLabs step:

```
git clone https://github.com/SunWeb3Sec/DeFiHackLabs.git data/raw/DeFiHackLabs
```

The committed `flash_loan_attacks_v2.csv` reflects manual corrections applied after
extraction: two incidents recorded under different protocol names were the same event, and
one date was wrong by two months. The deduplication key cannot merge one incident recorded
under two names, so the output of a fresh run will differ from the committed file.

## Scope and limitations

- **Allium access is required** to run any query here. The raw data is not redistributed.
- **Results were produced with scikit-learn 1.9.0** and Python 3.11. No dependency
  manifest is included; the collection scripts need only `requests` and `beautifulsoup4`.
- **The RQ3 analysis scripts are included; the plotting scripts are not.**
- **The RQ3 scripts cannot be run end to end from this repository.** They read a feature
  table, `analysis/rq3_results/profiles_flat.csv`, which is not redistributed here. That file
  is produced by `rq3_structural_comparison.py` from full transaction call traces, fetched with
  an external profiling tool against an Ethereum archive node. The scripts are included so the
  feature definitions, the sampling, the cross-validation design and the metric computation can
  be read and checked; reproducing the numbers requires archive-node access and the profiling
  step.
- **Ground truth is a snapshot.** Contract registries and incident lists were verified at
  the dates recorded in each file and will drift as protocols deploy new contracts.

## Licensing

The queries (`sql/`), the collection scripts (`src/`), and the hand-curated ground truth
are MIT licensed — see `LICENSE`.

The result files derived from Allium queries, and the DeFiLlama snapshots, are **not**
covered by that license and remain subject to their sources' terms. They are included so
the figures reported in the thesis can be checked, not for redistribution. `DATA-LICENSE`
states which file falls under which.

If you want to build on this work, the queries are free to use — re-run them against your
own Allium access rather than reusing the result files here.

## Citation

If you use this material, please cite the thesis. On-chain data is sourced from Allium.
