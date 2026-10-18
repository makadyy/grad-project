"""Adversarial checks for the A1 data pipeline on tiny synthetic data."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score

HERE = Path(__file__).resolve().parent
failures = []


def check(name, condition, detail=""):
    print(("PASS" if condition else "FAIL"), name, detail)
    if not condition:
        failures.append((name, detail))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    raw = root / "raw"
    raw.mkdir()
    rows = [
        ["f1", "10.0", "20.0", "1", "2", "2020", "1.0", "2.0", "Benign", "-1"],
        ["f2", "11.0", "21.0", "1", "2", "2020", "2.0", "3.0", "Attack", "-1"],
        ["f3", "13.0", "22.0", "1", "2", "2020", "inf", "4.0", "Attack", "-1"],
        ["f2", "11.0", "21.0", "1", "2", "2020", "2.0", "3.0", "Attack", "-1"],
        ["f4", "12.0", "23.0", "1", "2", "2020", "4.0", "5.0", "Attempted", "1"],
        ["f5", "14.0", "24.0", "1", "2", "2020", "1e40", "6.0", "Attack", "-1"],
        ["Flow ID", "Src IP", "Dst IP", "Src Port", "Dst Port", "Timestamp", "F1", "F2", "Label", "AttemptedCategory"],
    ]
    cols = ["Flow ID", "Src IP", "Dst IP", "Src Port", "Dst Port", "Timestamp", "F1", "F2", "Label", "AttemptedCategory"]
    pd.DataFrame(rows, columns=cols).to_csv(raw / "day.csv", index=False)

    os.environ["CSV_DIR"] = str(raw)
    m01 = load_module(HERE / "01_prepare_parquet.py", "a1_step01")
    m01.OUT_DIR = str(root / "out01")
    m01.PQ_DIR = str(root / "out01" / "parquet")
    m01.main()
    out = next((root / "out01" / "parquet").glob("*.parquet"))
    clean = pd.read_parquet(out)
    check("clean parquet exists", len(clean) > 0)
    check("identifiers removed", not any(c.lower() in {"flow id", "src ip", "dst ip", "src port", "dst port", "timestamp"} for c in clean.columns))
    check("float32 features", all(str(clean[c].dtype) == "float32" for c in clean.columns if c not in ("Label", "Day")))
    check("attempted relabelled", "Benign" in set(clean["Label"]))
    stats = json.loads((root / "out01" / "clean_stats.json").read_text())
    check("nonfinite and float32 overflow removed", len(clean) == 3 and stats["totals"]["float32_overflow"] == 1, str(stats["totals"]))
    check("exact duplicate removed", stats["totals"]["dup"] == 1)

    # Build a rest set where one candidate is constant in train but varies in val/test.
    n = 100
    labels = np.array(["A", "B"] * (n // 2))
    idx = np.arange(n)
    tr_idx, tmp_idx = train_test_split(idx, test_size=0.30, stratify=labels, random_state=42)
    va_idx, te_idx = train_test_split(tmp_idx, test_size=0.50, stratify=labels[tmp_idx], random_state=42)
    cand = np.zeros(n, dtype=float)
    cand[va_idx] = 1.0
    cand[te_idx] = 2.0
    rest = pd.DataFrame({"candidate": cand, "useful": np.arange(n, dtype=float), "Label": labels, "Day": "rest"})
    unseen = pd.DataFrame({"candidate": [3.0] * 10, "useful": np.arange(10, dtype=float), "Label": ["A", "B"] * 5, "Day": "Wednesday-28-02-2018"})
    data_dir = root / "out02"
    (data_dir / "parquet").mkdir(parents=True)
    rest.to_parquet(data_dir / "parquet" / "rest.parquet", index=False)
    unseen.to_parquet(data_dir / "parquet" / "Wednesday-28-02-2018.parquet", index=False)
    m02 = load_module(HERE / "02_eda_split.py", "a1_step02")
    m02.OUT = str(data_dir)
    old_argv = sys.argv
    sys.argv = ["02_eda_split.py"]
    try:
        m02.main()
    finally:
        sys.argv = old_argv
    feats = json.loads((data_dir / "feature_columns.json").read_text())
    check("constant feature selection uses train only", "candidate" not in feats)
    train = pd.read_parquet(data_dir / "train.parquet")
    val = pd.read_parquet(data_dir / "val.parquet")
    test = pd.read_parquet(data_dir / "test.parquet")
    unseen_out = pd.read_parquet(data_dir / "unseen_day.parquet")
    check("split has no day leakage", set(train.Day) == {"rest"} and set(val.Day) == {"rest"} and set(test.Day) == {"rest"} and set(unseen_out.Day) == {"Wednesday-28-02-2018"})
    check("split roughly 70/15/15", len(train) == 70 and len(val) == 15 and len(test) == 15, f"{len(train)}/{len(val)}/{len(test)}")

    # Verify the implemented evaluation-label policy by executing the same behavior.
    y_true, y_pred = ["Seen", "Unseen"], ["Seen", "Seen"]
    metric_labels = sorted(set(y_true) | set(y_pred))
    actual = f1_score(y_true, y_pred, average="macro", labels=metric_labels, zero_division=0)
    expected = f1_score(y_true, y_pred, average="macro", labels=["Seen", "Unseen"], zero_division=0)
    check("unseen classes included in metric behavior", actual == expected and actual < 1.0, f"actual={actual}")

    # Numeric and textual AttemptedCategory values; unknown text is counted, not relabelled.
    raw2 = root / "attempted"
    raw2.mkdir()
    rows2 = [[f"id{i}", "src", "dst", str(i+1), "2", "2020", str(i+1), "2", "Attack", category]
             for i, category in enumerate(["-1", "0", "1", "Attempted", "mystery"])]
    pd.DataFrame(rows2, columns=cols).to_csv(raw2 / "day.csv", index=False)
    os.environ["CSV_DIR"] = str(raw2)
    m01b = load_module(HERE / "01_prepare_parquet.py", "a1_attempted")
    m01b.OUT_DIR = str(root / "out_attempted")
    m01b.PQ_DIR = str(root / "out_attempted" / "parquet")
    m01b.main()
    stats2 = json.loads((root / "out_attempted" / "clean_stats.json").read_text())["days"]["day"]
    clean2 = pd.read_parquet(root / "out_attempted" / "parquet" / "day.parquet")
    check("attempted category parsing and unknown audit", stats2["attempted_to_benign"] == 2 and stats2["attempted_category_unknown"] == 1 and "mystery" in stats2["attempted_category_unknown_values"] and (clean2["Label"] == "Benign").sum() == 2)
    check("raw and dedup per-day label counts", stats2["raw_label_counts_before_dedup"]["Attack"] == 3 and stats2["dedup_label_counts"]["Attack"] == 3)

    # ZIP traversal should be rejected before any member is written.
    import zipfile
    evil_zip = root / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as z:
        z.writestr("../escaped.csv", "bad")
    m01b.ZIP_PATH = str(evil_zip)
    m01b.CSV_DIR = str(root / "extract")
    try:
        m01b.extract()
        safe_zip = False
    except ValueError:
        safe_zip = not (root / "escaped.csv").exists()
    check("ZIP traversal rejected", safe_zip)

    # Small-class split should complete and transparently record train-only allocation.
    tiny_dir = root / "tiny"
    (tiny_dir / "parquet").mkdir(parents=True)
    tiny_frame = pd.DataFrame({"x": range(8), "Label": ["rare"] + ["common"] * 7, "Day": ["rest"] * 8})
    hold_frame = pd.DataFrame({"x": [9], "Label": ["common"], "Day": ["Wednesday-28-02-2018"]})
    tiny_frame.to_parquet(tiny_dir / "parquet" / "rest.parquet", index=False)
    hold_frame.to_parquet(tiny_dir / "parquet" / "hold.parquet", index=False)
    m02b = load_module(HERE / "02_eda_split.py", "a1_tiny")
    m02b.OUT = str(tiny_dir)
    old_argv = sys.argv; sys.argv = ["02_eda_split.py"]
    try: m02b.main()
    finally: sys.argv = old_argv
    tiny_alloc = json.loads((tiny_dir / "split_allocations.json").read_text())["classes"]
    check("tiny class allocation reported without crash", tiny_alloc["rare"]["train"] == 1 and tiny_alloc["rare"]["val"] == 0 and tiny_alloc["rare"]["test"] == 0)

    # Adversarial support sweep: two classes at every count 1..12. In
    # particular 5-8 exercise sklearn's fragile second-stage stratification.
    edge_ok = True
    edge_details = []
    for support in range(1, 13):
        edge_dir = root / f"edge_{support}"
        (edge_dir / "parquet").mkdir(parents=True)
        edge = pd.DataFrame({"x": np.arange(2 * support),
                             "Label": ["A"] * support + ["B"] * support,
                             "Day": ["rest"] * (2 * support)})
        edge_hold = pd.DataFrame({"x": [999], "Label": ["A"], "Day": ["Wednesday-28-02-2018"]})
        edge.to_parquet(edge_dir / "parquet" / "rest.parquet", index=False)
        edge_hold.to_parquet(edge_dir / "parquet" / "hold.parquet", index=False)
        edge_module = load_module(HERE / "02_eda_split.py", f"a1_edge_{support}")
        edge_module.OUT = str(edge_dir)
        old_argv = sys.argv
        sys.argv = ["02_eda_split.py"]
        try:
            edge_module.main()
        except Exception as exc:
            edge_ok = False
            edge_details.append(f"n={support}: {type(exc).__name__}: {exc}")
        finally:
            sys.argv = old_argv
        if not (edge_dir / "split_allocations.json").exists():
            edge_ok = False
            continue
        report = json.loads((edge_dir / "split_allocations.json").read_text())["classes"]
        for label in ("A", "B"):
            rec = report[label]
            allocated = sum(rec[k] for k in ("train", "val", "test"))
            ratio_sum = sum(rec["actual_ratios"].values())
            if rec["total"] != support or allocated != support or not np.isclose(ratio_sum, 1.0):
                edge_ok = False
                edge_details.append(f"n={support} {label}: {rec}")
        if support < 5 and any(report[label][part] for label in ("A", "B") for part in ("val", "test")):
            edge_ok = False
            edge_details.append(f"n={support}: unsupported tiny class leaked outside train")
    check("two-class supports 1-12 allocate deterministically with actual-ratio disclosure", edge_ok, "; ".join(edge_details))

print("FAILURES", failures)
raise SystemExit(1 if failures else 0)
