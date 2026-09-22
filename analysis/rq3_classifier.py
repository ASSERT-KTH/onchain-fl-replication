"""
RQ3 supervised separability: can the six structural features tell attack
transactions apart from benign ones when read together rather than one at a time?

Input:
  - analysis/rq3_results/profiles_flat.csv  (904 rows: 30 attack, 874 benign)
    The same file behind summary_stats.json and the RQ3 feature table.

Method:
  Random forest, library defaults, no hyperparameter tuning. With 30 attack
  transactions there is not enough data to tune on without fitting the tuning
  to the sample, so the defaults are used and reported as such.

  Five-fold cross-validation, stratified so each fold holds the same
  attack/benign proportion. A single train/test split would leave about five
  attacks in the test set, where one transaction moves recall by twenty points.
  Under cross-validation every transaction is predicted exactly once, by a model
  that did not see it during training, and the pooled predictions give one
  result computed from all the data.

  A majority-class baseline (predict benign always) is reported alongside, to
  show what the accuracy figure looks like when the model has learned nothing.

Outputs (analysis/rq3_results/classifier/):
  - metrics.json         pooled scores, per-fold scores, confusion matrix
  - feature_importance.json
"""

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).parent.parent
PROFILES = ROOT / "analysis" / "rq3_results" / "profiles_flat.csv"
OUT = ROOT / "analysis" / "rq3_results" / "classifier"

# The six features defined in Section 3.3.3. tx_hash is an identifier, and meta
# holds the protocol name for attacks but the quarter for benign transactions,
# so including either would let the model read the label off the input.
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


def load_dataset():
    """Read profiles_flat.csv into a feature matrix and a binary label vector."""
    rows = list(csv.DictReader(PROFILES.open()))

    skipped = [r for r in rows if r.get("status") != "success"]
    if skipped:
        raise ValueError(
            f"{len(skipped)} rows are not status=success; the feature table assumes "
            "all 904 profiles succeeded. Investigate before training."
        )

    features = np.array([[float(r[f]) for f in FEATURES] for r in rows])
    labels = np.array([1 if r["label"] == "attack" else 0 for r in rows])
    return features, labels


def evaluate(features, labels):
    """Cross-validate the forest, predicting every transaction exactly once."""
    folds = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)

    predictions = np.zeros(len(labels), dtype=int)
    per_fold = []

    for fold_index, (train_idx, test_idx) in enumerate(folds.split(features, labels), 1):
        model = RandomForestClassifier(
            # class_weight balances the 30-against-874 split so the forest is not
            # rewarded for ignoring the attack class entirely.
            class_weight="balanced",
            random_state=SEED,
        )
        model.fit(features[train_idx], labels[train_idx])
        fold_predictions = model.predict(features[test_idx])
        predictions[test_idx] = fold_predictions

        precision, recall, f1, _ = precision_recall_fscore_support(
            labels[test_idx], fold_predictions, labels=[1], zero_division=0
        )
        per_fold.append(
            {
                "fold": fold_index,
                "attacks_in_fold": int(labels[test_idx].sum()),
                "precision": round(float(precision[0]), 4),
                "recall": round(float(recall[0]), 4),
                "f1": round(float(f1[0]), 4),
            }
        )

    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, labels=[1], zero_division=0
    )
    tn, fp, fn, tp = confusion_matrix(labels, predictions).ravel()

    return {
        "pooled": {
            "precision": round(float(precision[0]), 4),
            "recall": round(float(recall[0]), 4),
            "f1": round(float(f1[0]), 4),
            "accuracy": round(float((predictions == labels).mean()), 4),
        },
        "confusion_matrix": {
            "true_positive": int(tp),
            "false_negative": int(fn),
            "false_positive": int(fp),
            "true_negative": int(tn),
        },
        "per_fold": per_fold,
        "fold_f1_range": [
            round(min(f["f1"] for f in per_fold), 4),
            round(max(f["f1"] for f in per_fold), 4),
        ],
    }


def majority_baseline(labels):
    """Predict benign for every transaction: the model that learns nothing."""
    predictions = np.zeros(len(labels), dtype=int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, predictions, labels=[1], zero_division=0
    )
    return {
        "description": "predicts benign for every transaction",
        "accuracy": round(float((predictions == labels).mean()), 4),
        "precision": round(float(precision[0]), 4),
        "recall": round(float(recall[0]), 4),
        "f1": round(float(f1[0]), 4),
    }


def rank_features(features, labels):
    """Rank features by how much shuffling each one degrades the forest.

    Permutation importance is used rather than the forest's built-in Gini
    importance, which is inflated for continuous features such as gas_used
    relative to small-integer ones such as max_depth.
    """
    model = RandomForestClassifier(class_weight="balanced", random_state=SEED)
    model.fit(features, labels)

    result = permutation_importance(
        model, features, labels, n_repeats=20, random_state=SEED, scoring="f1"
    )

    ranking = [
        {
            "feature": name,
            "importance": round(float(result.importances_mean[i]), 4),
            "sd": round(float(result.importances_std[i]), 4),
        }
        for i, name in enumerate(FEATURES)
    ]
    ranking.sort(key=lambda entry: entry["importance"], reverse=True)
    return ranking


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    features, labels = load_dataset()

    print(f"Loaded {len(labels)} transactions: "
          f"{int(labels.sum())} attack, {int((labels == 0).sum())} benign")
    print(f"Features: {', '.join(FEATURES)}\n")

    metrics = evaluate(features, labels)
    metrics["baseline_majority_class"] = majority_baseline(labels)
    metrics["config"] = {
        "model": "RandomForestClassifier (scikit-learn defaults)",
        "n_estimators": 100,
        "class_weight": "balanced",
        "hyperparameter_tuning": "none",
        "cross_validation": f"stratified {N_FOLDS}-fold",
        "random_state": SEED,
        "n_attack": int(labels.sum()),
        "n_benign": int((labels == 0).sum()),
    }

    importance = rank_features(features, labels)

    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (OUT / "feature_importance.json").write_text(json.dumps(importance, indent=2))

    pooled = metrics["pooled"]
    cm = metrics["confusion_matrix"]
    base = metrics["baseline_majority_class"]

    print("=== Attack class, pooled over folds ===")
    print(f"  precision {pooled['precision']:.3f}   "
          f"recall {pooled['recall']:.3f}   f1 {pooled['f1']:.3f}")
    print(f"  caught {cm['true_positive']}/{cm['true_positive'] + cm['false_negative']} attacks, "
          f"{cm['false_positive']} benign flagged as attack")
    print(f"  per-fold f1 range: {metrics['fold_f1_range'][0]:.3f} to {metrics['fold_f1_range'][1]:.3f}")

    print("\n=== Majority-class baseline ===")
    print(f"  accuracy {base['accuracy']:.3f} (forest: {pooled['accuracy']:.3f}), f1 {base['f1']:.3f}")

    print("\n=== Feature importance (permutation) ===")
    for entry in importance:
        print(f"  {entry['feature']:24s} {entry['importance']:+.4f}  (sd {entry['sd']:.4f})")

    print(f"\nWrote {OUT}/metrics.json and feature_importance.json")


if __name__ == "__main__":
    main()
