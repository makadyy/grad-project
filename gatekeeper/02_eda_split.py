"""
Step 2: EDA per capture day + data card, constant-column removal, stratified 70/15/15 split
with an unseen-day hold-out. Reads out/parquet/*.parquet (from 01_prepare_parquet.py).

Outputs in out/:  train.parquet, val.parquet, test.parquet, unseen_day.parquet,
                  eda_classes_per_day.csv, DATA_CARD.md, feature_columns.json
Run:  python 02_eda_split.py [--holdout-day Wednesday-28-02-2018]
"""
import argparse
import glob
import json
import os

import pandas as pd
from sklearn.model_selection import train_test_split

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SEED = 42


def main():
    ap = argparse.ArgumentParser()
    # Wednesday-28-02 holds Infiltration, which also appears on Thursday-01-03,
    # so the model has seen that class on other days (a fair unseen-DAY test).
    ap.add_argument("--holdout-day", default="Wednesday-28-02-2018")
    args = ap.parse_args()

    df = pd.concat([pd.read_parquet(p) for p in sorted(glob.glob(os.path.join(OUT, "parquet", "*.parquet")))],
                   ignore_index=True)
    feats = [c for c in df.columns if c not in ("Label", "Day")]

    # ---- EDA: classes per capture day
    per_day = pd.crosstab(df["Day"], df["Label"])
    per_day.to_csv(os.path.join(OUT, "eda_classes_per_day.csv"))
    # clean_stats retains each day's distribution before cross-day deduplication
    # alongside its post-dedup distribution, so the amount removed is auditable.
    stats_path = os.path.join(OUT, "clean_stats.json")
    if os.path.exists(stats_path):
        with open(stats_path, encoding="utf-8") as f:
            clean_stats = json.load(f)
        rows = []
        for day, info in clean_stats.get("days", {}).items():
            for label, count in info.get("raw_label_counts_before_dedup", {}).items():
                rows.append({"Day": day, "Label": label, "count_basis": "raw_before_global_dedup", "count": count})
            for label, count in info.get("dedup_label_counts", {}).items():
                rows.append({"Day": day, "Label": label, "count_basis": "deduplicated_kept", "count": count})
        pd.DataFrame(rows, columns=["Day", "Label", "count_basis", "count"]).to_csv(
            os.path.join(OUT, "eda_classes_per_day_raw_and_dedup.csv"), index=False)
    print(per_day.T.to_string())

    # ---- hold out one entire day, split the rest
    hold_mask = df["Day"].eq(args.holdout_day)
    if not hold_mask.any():
        raise SystemExit(f"holdout day {args.holdout_day!r} not found in {sorted(df['Day'].unique())}")
    unseen, rest = df[hold_mask], df[~hold_mask]

    # Prefer sklearn's standard two-stage stratification when every class can
    # support it. Its second-stage split can still fail for small/uneven supports
    # (notably class counts 5-8), so fall back to deterministic allocations.
    cnt = rest["Label"].value_counts()
    allocations = {}
    if len(cnt) and int(cnt.min()) >= 5:
        try:
            train, tmp = train_test_split(rest, test_size=0.30, stratify=rest["Label"], random_state=SEED)
            val, test = train_test_split(tmp, test_size=0.50, stratify=tmp["Label"], random_state=SEED)
        except ValueError:
            train = val = test = None
    else:
        train = val = test = None
    if train is None:
        import numpy as np
        rng = np.random.default_rng(SEED)
        parts = {name: [] for name in ("train", "val", "test")}
        for label, group in rest.groupby("Label", sort=True):
            ix = rng.permutation(group.index.to_numpy()); n = len(ix)
            if n < 5:
                counts = (n, 0, 0)
            else:
                nv = max(1, int(round(n * .15))); nt = max(1, int(round(n * .15)))
                counts = (n - nv - nt, nv, nt)
            allocations[str(label)] = {"total": n, "train": counts[0], "val": counts[1], "test": counts[2],
                "actual_ratios": {k: v / n for k, v in zip(("train", "val", "test"), counts)},
                "deviation_from_70_15_15": {k: v / n - t for k, v, t in zip(("train", "val", "test"), counts, (.70, .15, .15))}}
            start = 0
            for name, number in zip(("train", "val", "test"), counts):
                parts[name].append(group.loc[ix[start:start + number]]); start += number
        train, val, test = (pd.concat(parts[n]) if parts[n] else rest.iloc[0:0].copy() for n in ("train", "val", "test"))
        train = train.sample(frac=1, random_state=SEED)
    if not allocations:
        for label, group in rest.groupby("Label", sort=True):
            n = len(group); counts = tuple(int((part["Label"] == label).sum()) for part in (train, val, test))
            allocations[str(label)] = {"total": n, "train": counts[0], "val": counts[1], "test": counts[2],
                "actual_ratios": {k: v / n for k, v in zip(("train", "val", "test"), counts)},
                "deviation_from_70_15_15": {k: v / n - t for k, v, t in zip(("train", "val", "test"), counts, (.70, .15, .15))}}

    # Fit feature selection on train only; validation/test must not influence it.
    const = [c for c in feats if train[c].nunique() <= 1]
    feats = [c for c in feats if c not in const]

    keep = feats + ["Label", "Day"]
    for name, part in (("train", train), ("val", val), ("test", test), ("unseen_day", unseen)):
        part[keep].to_parquet(os.path.join(OUT, f"{name}.parquet"), index=False)
    with open(os.path.join(OUT, "feature_columns.json"), "w") as f:
        json.dump(feats, f, indent=2)
    with open(os.path.join(OUT, "split_allocations.json"), "w") as f:
        json.dump({"target_ratios": {"train": .70, "val": .15, "test": .15}, "classes": allocations}, f, indent=2)

    # ---- data card
    lines = [
        "# Data Card - Gatekeeper dataset (CSE-CIC-IDS2018, corrected by Liu et al. 2022)", "",
        "- **Source:** https://intrusion-detection.distrinet-research.be/CNS2022/ (CSECICIDS2018_improved.zip)",
        "- **Citation:** Liu, Engelen, Lynar, Essam, Joosen. *Error Prevalence in NIDS datasets*, IEEE CNS 2022.",
        "- **Format:** Parquet, features float32, string `Label`, `Day` column.",
        "- **Cleaning:** repeated headers, non-finite (Inf/NaN) rows and exact duplicates removed; identifier "
        "columns (IPs, ports, Flow ID, timestamp) dropped; 'Attempted' flows relabelled Benign (authors' advice); "
        f"{len(const)} constant columns dropped: {const}.",
        f"- **Features kept:** {len(feats)}",
        f"- **Split:** unseen-day hold-out = `{args.holdout_day}` ({len(unseen):,} rows); remaining days split "
        f"stratified 70/15/15 (seed {SEED}): train {len(train):,} / val {len(val):,} / test {len(test):,}.",
        "- **Per-class split allocations:** counts, actual ratios, and deviations from target ratios are in `split_allocations.json`.", "",
        "## Rows per class per capture day", "", per_day.T.to_markdown(), "",
        "## Rows per class per split", "",
        pd.DataFrame({"train": train["Label"].value_counts(), "val": val["Label"].value_counts(),
                      "test": test["Label"].value_counts(),
                      "unseen_day": unseen["Label"].value_counts()}).fillna(0).astype(int).to_markdown(), "",
    ]
    with open(os.path.join(OUT, "DATA_CARD.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Wrote splits + DATA_CARD.md")


if __name__ == "__main__":
    main()
