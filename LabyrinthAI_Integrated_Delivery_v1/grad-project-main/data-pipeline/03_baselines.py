"""
Step 3: baselines. Trains Decision Tree + XGBoost on train, reports macro-F1 / per-class
metrics on val, test and the unseen-day set. Run: python 03_baselines.py
"""
import json
import os

import pandas as pd
from sklearn.metrics import classification_report, f1_score
from sklearn.preprocessing import LabelEncoder
from sklearn.tree import DecisionTreeClassifier
from xgboost import XGBClassifier

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def load(name, feats):
    d = pd.read_parquet(os.path.join(OUT, f"{name}.parquet"))
    return d[feats].values, d["Label"].values


def main():
    feats = json.load(open(os.path.join(OUT, "feature_columns.json")))
    Xtr, ytr = load("train", feats)
    if len(ytr) == 0:
        raise SystemExit("train split is empty - re-run 02_eda_split.py with more data")
    if len(set(ytr)) < 2:
        raise SystemExit("train split has a single class - baselines need at least 2 classes")
    le = LabelEncoder().fit(ytr)
    ytr = le.transform(ytr)
    sets = {n: load(n, feats) for n in ("val", "test", "unseen_day")}

    models = {
        "decision_tree": DecisionTreeClassifier(max_depth=20, class_weight="balanced", random_state=42),
        "xgboost": XGBClassifier(n_estimators=200, max_depth=8, learning_rate=0.2, tree_method="hist",
                                 n_jobs=-1, random_state=42),
    }
    results = {}
    for mname, m in models.items():
        print(f"Training {mname} ...", flush=True)
        m.fit(Xtr, ytr)
        for sname, (X, y) in sets.items():
            if len(y) == 0:
                # Policy: an empty eval split is reported as null (not scored) instead of crashing,
                # so the other splits are still evaluated. The skip is visible in the JSON + stdout.
                print(f"[{mname}] {sname}: EMPTY split - skipped (reported as null)")
                results[f"{mname}/{sname}"] = None
                continue
            pred = le.inverse_transform(m.predict(X))
            # Score every class that is really present (true) or predicted. Classes that appear
            # only in this eval set (e.g. unseen-day) are included; train classes absent from
            # both y and pred are NOT, otherwise a perfect model scores far below 1.0.
            metric_labels = sorted(set(y) | set(pred))
            f1 = f1_score(y, pred, average="macro", labels=metric_labels, zero_division=0)
            results[f"{mname}/{sname}"] = round(float(f1), 4)
            print(f"[{mname}] {sname}: macro-F1={f1:.4f}")
            if sname == "unseen_day":
                print(classification_report(y, pred, zero_division=0))
    json.dump(results, open(os.path.join(OUT, "baseline_results.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
