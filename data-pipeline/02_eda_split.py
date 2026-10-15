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
    print(per_day.T.to_string())

    # ---- hold out one entire day, split the rest
    hold_mask = df["Day"].str.startswith(args.holdout_day)
    if not hold_mask.any():
        raise SystemExit(f"holdout day {args.holdout_day!r} not found in {sorted(df['Day'].unique())}")
    unseen, rest = df[hold_mask], df[~hold_mask]

    # constant columns: decided on the training side only (rest), applied to everything
    const = [c for c in feats if rest[c].nunique() <= 1]
    feats = [c for c in feats if c not in const]

    # stratified split; classes with <3 rows can't be stratified -> put all in train
    cnt = rest["Label"].value_counts()
    tiny = rest["Label"].isin(cnt[cnt < 3].index)
    main_df, tiny_df = rest[~tiny], rest[tiny]
    train, tmp = train_test_split(main_df, test_size=0.30, stratify=main_df["Label"], random_state=SEED)
    val, test = train_test_split(tmp, test_size=0.50, stratify=tmp["Label"], random_state=SEED)
    train = pd.concat([train, tiny_df])

    keep = feats + ["Label", "Day"]
    for name, part in (("train", train), ("val", val), ("test", test), ("unseen_day", unseen)):
        part[keep].to_parquet(os.path.join(OUT, f"{name}.parquet"), index=False)
    with open(os.path.join(OUT, "feature_columns.json"), "w") as f:
        json.dump(feats, f, indent=2)

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
        "- **Known caveat:** very rare classes (<3 rows) go to train only.", "",
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
