"""A2 SHAP smoke test: trains a real XGBoost tree model on the 30 A2 features
(synthetic data with one planted signal) and checks that ShapService returns
the right feature names in the right order. Run from this folder:
    pip install shap
    python a2_shap_smoke.py
This tests the plumbing/compatibility only - NOT the team's real trained model."""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "grad-project-main" / "seif_profiler_xai" / "src"))

import numpy as np
from xgboost import XGBClassifier
from profiler_xai.feature_extractor import FEATURE_NAMES
from profiler_xai.shap_service import ShapService

NAMES = list(FEATURE_NAMES)
PLANTED = "login_failure_count"
FAILS = []

def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAILS.append(name)

print(f"features: {len(NAMES)}, planted signal on: {PLANTED}")
check("planted feature is one of the 30 features", PLANTED in NAMES)
i = NAMES.index(PLANTED)

rng = np.random.default_rng(0)
X = rng.random((600, len(NAMES)))
targets = {
    "binary (2 classes)": (X[:, i] > 0.5).astype(int),
    "multiclass (3 classes)": (X[:, i] > 0.33).astype(int) + (X[:, i] > 0.66).astype(int),
}

for label, y in targets.items():
    print(f"\n== {label} ==")
    model = XGBClassifier(n_estimators=60, max_depth=3, random_state=0, tree_method="hist")
    model.fit(X, y)
    svc = ShapService(model, NAMES)
    r = int(np.argmax(X[:, i]))                      # row with a very high planted value
    row = dict(zip(NAMES, map(float, X[r])))
    try:
        out = svc.explain_one(row, top_k=5)
    except Exception as ex:
        check("explain_one runs on a trained XGBoost model", False, repr(ex))
        continue
    check("explain_one runs on a trained XGBoost model", True)
    top = out["top_features"]
    print("   top features:", [(t["feature"], round(t["shap_value"], 3)) for t in top])
    check("returns exactly 5 features", len(top) == 5)
    check("all returned names are real A2 features", all(t["feature"] in NAMES for t in top))
    check("returned values match the input row", all(abs(t["value"] - row[t["feature"]]) < 1e-9 for t in top))
    check("planted feature is ranked #1 (feature order is correct)", top[0]["feature"] == PLANTED)
    # negative control: wrong feature order must NOT give the same answer
    wrong = ShapService(model, list(reversed(NAMES)))
    bad = wrong.explain_one(dict(zip(NAMES, map(float, X[r]))), top_k=1)["top_features"][0]["feature"]
    print("   (info) with reversed feature order the top feature would be:", bad)
    check("test is sensitive to wrong feature order", bad != PLANTED)

print("\n" + ("ALL SHAP CHECKS PASSED" if not FAILS else "FAILED: " + "; ".join(FAILS)))
sys.exit(1 if FAILS else 0)
