"""
RQ3: structural feature comparison between known flash loan attack transactions
and benign flash loan transactions.

Inputs:
  - data/ground_truth/flash_loan_attacks_v2.csv  (attack txs, has_flashloan_event=yes)
  - data/rq3_benign_sample_stratified.csv        (benign txs, n=874, ~38/quarter)

Pipeline:
  1. Extract tx hashes for each group
  2. Run tx-profiler on all hashes (skips if profile already cached on disk)
  3. Parse JSON profiles into a flat dataframe
  4. Produce summary stats + boxplots for key structural features
  5. Save results to analysis/rq3_results/
"""

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data" / "ground_truth"
OUT  = Path(__file__).parent / "rq3_results"
OUT.mkdir(exist_ok=True)

FEATURES = [
    "total_calls",
    "max_depth",
    "unique_contract_count",
    "unique_selector_count",
    "gas_used",
    "failed_subcalls",
    "high_contract_churn",
]


# 1. Extract hashes

def load_attack_hashes():
    hashes = []
    with open(DATA / "flash_loan_attacks_v2.csv") as f:
        for row in csv.DictReader(f):
            if row["tx_hash"].strip() and row["has_flashloan_event"].strip().lower() == "yes":
                hashes.append((row["tx_hash"].strip(), row["protocol"].strip()))
    return hashes


def load_benign_hashes():
    # Stratified benign sample: up to 38 FlashLoan transactions per quarter,
    # n=874. Benign is defined as "not a known attack"; the quarter is carried
    # as meta for reporting only.
    hashes = []
    with open(ROOT / "data" / "rq3_benign_sample_stratified.csv") as f:
        for row in csv.DictReader(f):
            tx = row["transaction_hash"].strip()
            if tx:
                hashes.append((tx, row.get("quarter", "").strip()))
    return hashes


# 2. Run tx-profiler (one hash at a time, cached)

PROFILE_CACHE = OUT / "profiles"
PROFILE_CACHE.mkdir(exist_ok=True)


def profile_tx(tx_hash: str) -> dict | None:
    cache_file = PROFILE_CACHE / f"{tx_hash}.json"
    if cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)

    print(f"  profiling {tx_hash[:12]}…", flush=True)
    result = subprocess.run(
        ["tx-profiler", "profile", tx_hash],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ERROR on {tx_hash}: {result.stderr.strip()[:120]}", file=sys.stderr)
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  JSON parse error on {tx_hash}", file=sys.stderr)
        return None

    with open(cache_file, "w") as f:
        json.dump(data, f)
    return data


# 3. Flatten profile → row

def flatten(profile: dict, label: str, meta: str) -> dict:
    calls     = profile.get("calls", {})
    contracts = profile.get("contracts", {})
    gas       = profile.get("gas", {})
    hints     = profile.get("flash_loan_hints", {})
    complexity = profile.get("complexity", {})
    identity  = profile.get("identity", {})

    return {
        "tx_hash":               identity.get("tx_hash", ""),
        "label":                 label,
        "meta":                  meta,
        "total_calls":           calls.get("total_calls", 0),
        "max_depth":             calls.get("max_depth", 0),
        "failed_subcalls":       calls.get("failed_subcalls", 0),
        "unique_contract_count": contracts.get("unique_contract_count", 0),
        "gas_used":              gas.get("gas_used", 0),
        "unique_selector_count": complexity.get("unique_selector_count", 0),
        "high_contract_churn":   int(hints.get("high_contract_churn", False)),
        "detected_providers":    len(hints.get("detected_providers", [])),
        "status":                identity.get("status", ""),
    }


# 4. Summary stats

def summary_stats(rows: list[dict], features: list[str]) -> dict:
    import statistics
    stats = {}
    for feat in features:
        vals = [r[feat] for r in rows if isinstance(r[feat], (int, float))]
        if not vals:
            continue
        stats[feat] = {
            "n":      len(vals),
            "mean":   round(statistics.mean(vals), 2),
            "median": round(statistics.median(vals), 2),
            "stdev":  round(statistics.stdev(vals), 2) if len(vals) > 1 else 0,
            "min":    min(vals),
            "max":    max(vals),
        }
    return stats


# 5. Plots

def make_plots(attack_rows, benign_rows):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plots")
        return

    plot_features = [
        ("total_calls",           "Total calls"),
        ("max_depth",             "Max call depth"),
        ("unique_contract_count", "Unique contracts"),
        ("gas_used",              "Gas used"),
        ("unique_selector_count", "Unique selectors"),
        ("failed_subcalls",       "Failed subcalls"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    fig.suptitle("Attack vs Benign — structural feature distributions", fontsize=13)

    for ax, (feat, title) in zip(axes.flat, plot_features):
        a_vals = [r[feat] for r in attack_rows]
        b_vals = [r[feat] for r in benign_rows]
        ax.boxplot([a_vals, b_vals], tick_labels=["Attack", "Benign"], patch_artist=True,
                   boxprops=dict(facecolor="#f4a261", alpha=0.7),
                   medianprops=dict(color="black", linewidth=2))
        ax.set_title(title)
        ax.set_ylabel(feat)

    plt.tight_layout()
    out_path = OUT / "structural_comparison.png"
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved → {out_path}")


# Main

def main():
    print("Loading hashes…")
    attack_hashes = load_attack_hashes()
    benign_hashes = load_benign_hashes()
    print(f"  Attack: {len(attack_hashes)} | Benign: {len(benign_hashes)}")

    print("\nProfiling attack txs…")
    attack_rows = []
    for tx_hash, protocol in attack_hashes:
        p = profile_tx(tx_hash)
        if p:
            attack_rows.append(flatten(p, "attack", protocol))

    print("\nProfiling benign txs…")
    benign_rows = []
    for tx_hash, use_case in benign_hashes:
        p = profile_tx(tx_hash)
        if p:
            benign_rows.append(flatten(p, "benign", use_case))

    print(f"\nSuccessfully profiled: {len(attack_rows)} attack, {len(benign_rows)} benign")

    # Save flat CSV
    all_rows = attack_rows + benign_rows
    if all_rows:
        csv_path = OUT / "profiles_flat.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"Flat CSV saved → {csv_path}")

    # Summary stats
    numeric_features = [
        "total_calls", "max_depth", "unique_contract_count",
        "gas_used", "unique_selector_count", "failed_subcalls",
    ]
    print("\n--- ATTACK ---")
    a_stats = summary_stats(attack_rows, numeric_features)
    for feat, s in a_stats.items():
        print(f"  {feat:28s}  median={s['median']:>10}  mean={s['mean']:>10}  max={s['max']:>10}")

    print("\n--- BENIGN ---")
    b_stats = summary_stats(benign_rows, numeric_features)
    for feat, s in b_stats.items():
        print(f"  {feat:28s}  median={s['median']:>10}  mean={s['mean']:>10}  max={s['max']:>10}")

    # Save stats JSON
    stats_path = OUT / "summary_stats.json"
    with open(stats_path, "w") as f:
        json.dump({"attack": a_stats, "benign": b_stats}, f, indent=2)
    print(f"\nStats saved → {stats_path}")

    make_plots(attack_rows, benign_rows)


if __name__ == "__main__":
    main()
