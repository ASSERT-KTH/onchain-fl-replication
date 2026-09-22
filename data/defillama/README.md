# DefiLlama TVL capture — 2026-07-01

**Purpose.** Provider market-structure figures for `2-background.tex` §2.3, pinned to the same
instant as the RQ1/RQ2 window boundary (2026-07-01 00:00 UTC) so background figures and measured
results describe the same market state.

**Source.** DefiLlama historical API, one call per protocol:
`https://api.llama.fi/protocol/{slug}`

Each response carries a daily `tvl` series (all chains) and `chainTvls.Ethereum.tvl`
(Ethereum only). The row selected is the series point nearest 2026-07-01 00:00 UTC; every
protocol returned an exact match (`offset_days = 0.0`).

**Retrieved.** 2026-08-18.

**Columns.**
- `tvl_eth` — Ethereum-only TVL, USD. **Use this one.** The thesis studies Ethereum mainnet.
- `tvl_all` — all-chains TVL, USD. Included to show the gap.
- `offset_days` — distance from the requested timestamp to the nearest series point.

**Caveat — DefiLlama categories are not flash loan categories.** The `category` field is
DefiLlama's own classification by primary business (Lending, Dexs, CDP). Spark and dYdX return
`null`, and version-split protocols (Aave V1/V2/V3) are separate entries sharing a
`parentProtocol`. Aggregating across versions is a judgement call, not something the API does.

**Caveat — TVL is not flash loan liquidity.** A protocol's TVL is what is deposited, not what is
available to borrow atomically, and no public platform reports flash loan volume as such. These
figures characterise market structure; they do not rank flash loan providers. That is the point
§2.3 makes, and the reason RQ1 identifies providers from on-chain event volume instead.

**Supersedes** the February 2026 figures previously in `2-background.tex` §2.3.2 (Aave $26.7B,
Uniswap $2.5B, Balancer $190M, dYdX $170M), which had no recorded provenance.
