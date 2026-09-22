"""
Per-attack cross-validation outcome for the RQ3 classifier.

Regenerates, for each of the 30 attack transactions, which fold predicted it and
whether that prediction was correct. The classifier in analysis/rq3_classifier.py
reports only the per-fold and pooled counts; this script recovers the underlying
per-transaction outcomes behind those counts.

The fold assignment and model are identical to rq3_classifier.py (same features,
same SEED, same StratifiedKFold), so the counts here sum to the pooled confusion
matrix in analysis/rq3_results/classifier/metrics.json.

Output: analysis/rq3_results/classifier/per_attack_outcomes.csv
"""

import csv
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).parent.parent
PROFILES = ROOT / "analysis" / "rq3_results" / "profiles_flat.csv"
OUT = ROOT / "analysis" / "rq3_results" / "classifier" / "per_attack_outcomes.csv"

FEATURES = [
    "gas_used",
    "total_calls",
    "unique_contract_count",
    "unique_selector_count",
    "max_depth",
    "failed_subcalls",
]

SEED = 42
N_FOLDS = 5


def main():
    rows = list(csv.DictReader(PROFILES.open()))
    X = np.array([[float(r[f]) for f in FEATURES] for r in rows])
    y = np.array([1 if r["label"] == "attack" else 0 for r in rows])

    outcomes = {}
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    for fold, (train, test) in enumerate(skf.split(X, y), 1):
        model = RandomForestClassifier(random_state=SEED, class_weight="balanced")
        model.fit(X[train], y[train])
        predicted = model.predict(X[test])
        for position, index in enumerate(test):
            if y[index] == 1:
                outcomes[index] = (fold, int(predicted[position]))

    records = []
    for index, (fold, predicted) in outcomes.items():
        row = rows[index]
        records.append(
            {
                "fold": fold,
                "incident": row["meta"],
                "tx_hash": row["tx_hash"],
                "gas_used": int(float(row["gas_used"])),
                "total_calls": int(float(row["total_calls"])),
                "unique_contract_count": int(float(row["unique_contract_count"])),
                "max_depth": int(float(row["max_depth"])),
                "outcome": "detected" if predicted else "missed",
            }
        )
    records.sort(key=lambda r: (r["fold"], r["incident"]))

    with OUT.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    detected = sum(1 for r in records if r["outcome"] == "detected")
    print(f"{len(records)} attack transactions: {detected} detected, {len(records) - detected} missed")
    print(f"written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
