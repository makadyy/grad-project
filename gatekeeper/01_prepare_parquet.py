"""
Step 1 (A1 Day 1-6): corrected CSE-CIC-IDS2018 (Liu et al. 2022) -> clean per-day Parquet (float32).

What it does, in order:
  1. Unzips gatekeeper/liu2022/CSECICIDS2018_improved.zip (once).
  2. Reads each day's CSV in chunks (low RAM).
  3. Cleaning:
       - drop repeated header rows
       - drop identifier columns (Flow ID, IPs, ports, timestamp)
       - "Attempted" flows -> relabelled Benign (what the Liu authors recommend)
       - Infinity / NaN -> row dropped
       - exact duplicates dropped (across ALL days)
  4. Saves out/parquet/<day>.parquet (features float32 + Label + Day) and out/clean_stats.json.
Constant-column removal happens in step 2 (it needs the training split only).

Run:  python 01_prepare_parquet.py
"""
import glob
import json
import os
import re
import zipfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(HERE, "liu2022", "CSECICIDS2018_improved.zip")
# Set env CSV_DIR to use already-downloaded CSVs (e.g. the original data in ./raw) instead of the zip.
CSV_DIR = os.environ.get("CSV_DIR", os.path.join(HERE, "liu2022", "csv"))
OUT_DIR = os.path.join(HERE, "out")
PQ_DIR = os.path.join(OUT_DIR, "parquet")
CHUNK = 200_000

# lowercase, spaces/underscores removed -> compare names loosely
IDENTIFIERS = {"flowid", "srcip", "sourceip", "dstip", "destinationip", "srcport", "sourceport",
               "dstport", "destinationport", "timestamp"}
# columns that are not numeric features (kept out of the feature matrix)
META = {"label", "attemptedcategory"}


def norm(c):
    return re.sub(r"[^a-z]", "", c.lower())


def extract():
    os.makedirs(CSV_DIR, exist_ok=True)
    if glob.glob(os.path.join(CSV_DIR, "**", "*.csv"), recursive=True):
        return
    print("Unzipping ...", flush=True)
    # Validate every archive member before extraction (including symlink entries).
    root = os.path.realpath(CSV_DIR)
    with zipfile.ZipFile(ZIP_PATH) as z:
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            target = os.path.realpath(os.path.join(root, name))
            if name.startswith("/") or os.path.commonpath([root, target]) != root:
                raise ValueError(f"Unsafe ZIP member path: {info.filename!r}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError(f"ZIP symlink member not allowed: {info.filename!r}")
        z.extractall(root)


def normalize_label(s):
    s = str(s).strip().replace("–", "-").replace("—", "-")
    return " ".join(s.split())


def main():
    extract()
    files = sorted(glob.glob(os.path.join(CSV_DIR, "**", "*.csv"), recursive=True))
    if not files:
        raise SystemExit("No CSV files found after unzip.")
    os.makedirs(PQ_DIR, exist_ok=True)

    seen = set()
    stats = {"days": {}, "totals": {}}
    tot = dict(raw=0, header=0, attempted_to_benign=0, nonfinite=0, float32_overflow=0, dup=0, kept=0)

    for fp in files:
        day = os.path.splitext(os.path.basename(fp))[0]
        out_path = os.path.join(PQ_DIR, f"{day}.parquet")
        d = dict(raw=0, header=0, attempted_to_benign=0, nonfinite=0, float32_overflow=0, dup=0, kept=0)
        raw_label_counts, dedup_label_counts = {}, {}
        writer = None
        print(f"== {day}", flush=True)
        for chunk in pd.read_csv(fp, dtype=str, chunksize=CHUNK, low_memory=False,
                                 skipinitialspace=True):
            chunk.columns = [c.strip() for c in chunk.columns]
            cmap = {norm(c): c for c in chunk.columns}
            label_col = cmap["label"]
            att_col = cmap.get("attemptedcategory")
            d["raw"] += len(chunk)

            # repeated header rows: a numeric column holds its own name
            probe = next(c for c in chunk.columns if norm(c) not in IDENTIFIERS | META)
            bad = pd.to_numeric(chunk[probe], errors="coerce").isna() & (chunk[probe] == probe)
            d["header"] += int(bad.sum())
            chunk = chunk.loc[~bad]
            if chunk.empty:
                continue

            labels = chunk[label_col].map(normalize_label)
            if att_col is not None:
                raw_attempted = chunk[att_col].astype(str).str.strip()
                numeric_attempted = pd.to_numeric(raw_attempted, errors="coerce")
                known_text = raw_attempted.str.lower().isin({"", "nan", "none", "null", "-1", "0", "false", "no", "1", "true", "yes", "attempted"})
                unknown = (~known_text & numeric_attempted.isna()) | (numeric_attempted.notna() & ~numeric_attempted.isin([-1, 0, 1]))
                d["attempted_category_unknown"] = d.get("attempted_category_unknown", 0) + int(unknown.sum())
                d["attempted_category_unknown_values"] = sorted(set(d.get("attempted_category_unknown_values", [])) | set(raw_attempted[unknown].unique().tolist()))
                attempted = numeric_attempted.eq(1) | raw_attempted.str.lower().isin({"attempted", "true", "yes"})
            else:
                attempted = labels.str.contains("attempted", case=False)
            d["attempted_to_benign"] += int(attempted.sum())
            labels = labels.where(~attempted, "Benign")
            for label, count in labels.value_counts().items():
                raw_label_counts[label] = raw_label_counts.get(label, 0) + int(count)

            feat_cols = [c for c in chunk.columns if norm(c) not in IDENTIFIERS | META]
            X = chunk[feat_cols].apply(pd.to_numeric, errors="coerce").astype("float64")
            ok = np.isfinite(X.values).all(axis=1)  # NaN and +-Infinity
            d["nonfinite"] += int((~ok).sum())
            X, labels = X.loc[ok], labels.loc[ok]
            if X.empty:
                continue

            # Reject values that cannot be represented by float32; do not silently clip
            # them into a different value.
            f32_max = np.finfo(np.float32).max
            fits_float32 = (X.abs() <= f32_max).all(axis=1)
            d["float32_overflow"] += int((~fits_float32).sum())
            X, labels = X.loc[fits_float32], labels.loc[fits_float32]
            if X.empty:
                continue
            X = X.astype("float32")
            h = pd.util.hash_pandas_object(X, index=False).values ^ \
                pd.util.hash_pandas_object(labels, index=False).values
            dup = np.fromiter((v in seen for v in h), dtype=bool, count=len(h))
            # also duplicates inside this very chunk
            _, first = np.unique(h, return_index=True)
            inchunk = np.ones(len(h), dtype=bool)
            inchunk[first] = False
            dup |= inchunk
            seen.update(h[~dup].tolist())
            d["dup"] += int(dup.sum())
            X, labels = X.loc[~dup], labels.loc[~dup]
            if X.empty:
                continue

            X = X.reset_index(drop=True)
            X["Label"] = labels.reset_index(drop=True)
            X["Day"] = day
            table = pa.Table.from_pandas(X, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out_path, table.schema, compression="zstd")
            writer.write_table(table)
            d["kept"] += len(X)
            kept_labels = labels.to_numpy()
            for label, count in pd.Series(kept_labels).value_counts().items():
                dedup_label_counts[label] = dedup_label_counts.get(label, 0) + int(count)
        d["raw_label_counts_before_dedup"] = raw_label_counts
        d["dedup_label_counts"] = dedup_label_counts
        if writer:
            writer.close()
        stats["days"][day] = d
        for k in tot:
            tot[k] += d[k]
        print(f"   {d}", flush=True)

    stats["totals"] = tot
    with open(os.path.join(OUT_DIR, "clean_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print("Done:", tot)


if __name__ == "__main__":
    main()
