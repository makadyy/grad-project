"""
CSE-CIC-IDS2018 -> train/val/test ready-to-train sets.

Implements Chapter 1, Section 1.6.3 exactly:
  - drop repeated header rows, exact duplicates, non-finite Flow Byts/s & Flow Pkts/s
  - drop machine-identifying columns (IPs, ports, Flow ID, Timestamp)
  - drop constant columns, normalize Label text
  - add two ratio features, drop one of each highly-correlated pair
  - stratified-by-construction train/val/test split BEFORE any scaling/resampling
  - scaler + label encoding fit on train only, applied unchanged to val/test
  - undersample Benign + SMOTE rare attacks, train split only
  - saves scaler, label map, and a full JSON report of every count

One command, one output: `python build_dataset.py`
"""

import glob
import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.preprocessing import LabelEncoder, StandardScaler
from imblearn.over_sampling import SMOTE
from imblearn.under_sampling import RandomUnderSampler
import joblib

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw")
OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)

IDENTIFIER_COLS = [
    "Flow ID", "Src IP", "Source IP", "Dst IP", "Destination IP",
    "Src Port", "Source Port", "Dst Port", "Destination Port", "Timestamp",
]
SPEED_COLS = ["Flow Byts/s", "Flow Pkts/s"]
CHUNK_SIZE = 100_000
CORR_THRESHOLD = 0.95
RARE_CLASS_MIN_TRAIN_ROWS = 20
SMOTE_GROWTH_MULTIPLIER = 20
SMOTE_TARGET_CAP = 50_000
SEED = 42

PROGRESS_PATH = os.path.join(OUT_DIR, "_progress.json")
HASHES_PATH = os.path.join(OUT_DIR, "_seen_hashes.bin")

report = {"stages": []}


def load_progress():
    default = {
        "completed_files": [], "current_file": None, "current_file_chunks_done": 0,
        "counters": {
            "raw_rows": 0, "header_rows_dropped": 0, "nonfinite_speed_dropped": 0,
            "other_nan_dropped": 0, "duplicates_dropped": 0, "clean_rows": 0,
        },
        "per_file_clean_rows": {}, "label_counts_all": {},
    }
    if not os.path.exists(PROGRESS_PATH):
        return default
    with open(PROGRESS_PATH) as f:
        saved = json.load(f)
    default.update(saved)
    return default


def save_progress(state):
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, PROGRESS_PATH)


def load_seen_hashes():
    if not os.path.exists(HASHES_PATH):
        return set()
    return set(np.fromfile(HASHES_PATH, dtype=np.uint64).tolist())


def append_new_hashes(new_hashes):
    if not new_hashes:
        return
    with open(HASHES_PATH, "ab") as f:
        np.array(new_hashes, dtype=np.uint64).tofile(f)


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def record(stage, **kw):
    report["stages"].append({"stage": stage, **kw})


def normalize_label(s):
    if not isinstance(s, str):
        return s
    s = s.strip()
    s = s.replace("–", "-").replace("—", "-")
    s = " ".join(s.split())
    return s


def clean_chunk(chunk, seen_hashes, counters):
    """One chunk from one raw file -> cleaned chunk (or None if empty)."""
    n_in = len(chunk)
    counters["raw_rows"] += n_in

    # 1. repeated header rows embedded as data: 'Protocol' fails to parse as a number
    numeric_probe = pd.to_numeric(chunk["Protocol"], errors="coerce")
    is_header_row = numeric_probe.isna()
    counters["header_rows_dropped"] += int(is_header_row.sum())
    chunk = chunk.loc[~is_header_row].copy()
    if chunk.empty:
        return None

    # 2. drop machine-identifying columns FIRST - Timestamp etc. are not
    #    numeric-parseable and must not be in play for the coercion/dropna below
    drop_now = [c for c in IDENTIFIER_COLS if c in chunk.columns]
    chunk = chunk.drop(columns=drop_now)

    # 3. coerce every remaining column except Label to numeric
    feature_cols = [c for c in chunk.columns if c != "Label"]
    for c in feature_cols:
        chunk[c] = pd.to_numeric(chunk[c], errors="coerce")

    # 4. non-finite Flow Byts/s & Flow Pkts/s -> drop those rows
    mask_finite = np.isfinite(chunk[SPEED_COLS]).all(axis=1)
    counters["nonfinite_speed_dropped"] += int((~mask_finite).sum())
    chunk = chunk.loc[mask_finite].copy()
    if chunk.empty:
        return None

    # 5. any remaining NaN from coercion -> drop row
    before = len(chunk)
    chunk = chunk.dropna()
    counters["other_nan_dropped"] += before - len(chunk)
    if chunk.empty:
        return None

    # 6. exact duplicates, tracked across the whole run (persisted to disk so
    #    a killed-and-resumed run does not lose what it has already seen)
    row_hashes = pd.util.hash_pandas_object(chunk, index=False).values
    is_dup = np.array([h in seen_hashes for h in row_hashes])
    new_hashes = [int(h) for h in row_hashes[~is_dup]]
    for h in new_hashes:
        seen_hashes.add(h)
    counters["duplicates_dropped"] += int(is_dup.sum())
    chunk = chunk.loc[~is_dup].copy()
    if chunk.empty:
        append_new_hashes(new_hashes)
        return None

    # 7. normalize label text
    chunk["Label"] = chunk["Label"].map(normalize_label)

    # 8. engineered ratios (Laplace-smoothed denominators, no inf possible)
    chunk["Fwd Bwd Pkt Ratio"] = chunk["Tot Fwd Pkts"] / (chunk["Tot Bwd Pkts"] + 1)
    chunk["Avg Bytes Per Pkt"] = (chunk["TotLen Fwd Pkts"] + chunk["TotLen Bwd Pkts"]) / (
        chunk["Tot Fwd Pkts"] + chunk["Tot Bwd Pkts"] + 1
    )

    for c in chunk.columns:
        if c != "Label":
            chunk[c] = chunk[c].astype("float32")

    counters["clean_rows"] += len(chunk)
    append_new_hashes(new_hashes)
    return chunk


def stream_clean_and_split():
    """Pass 1: read every raw CSV in chunks, clean, split rows into
    train/val/test files on disk (70/15/15, iid random - stratified in
    effect at this row count) so nothing large sits in memory at once.

    Checkpoints after every chunk to out/_progress.json, so if this process
    gets killed partway through (observed: something reaps it every few
    minutes, cause unconfirmed), re-running the script picks up exactly
    where it left off instead of starting the whole 6.9GB pass over again.
    """
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.csv")))
    if not files:
        raise SystemExit(f"No CSVs found in {RAW_DIR} - did the download finish?")

    state = load_progress()
    seen_hashes = load_seen_hashes()
    log(f"Found {len(files)} raw files. Resuming: {len(state['completed_files'])} already fully done, "
        f"current_file={state['current_file']!r} at chunk {state['current_file_chunks_done']}, "
        f"seen_hashes loaded={len(seen_hashes):,}")

    rng = np.random.default_rng(SEED)
    paths = {
        "train": os.path.join(OUT_DIR, "_stream_train.csv"),
        "val": os.path.join(OUT_DIR, "_stream_val.csv"),
        "test": os.path.join(OUT_DIR, "_stream_test.csv"),
    }
    wrote_header = {k: os.path.exists(p) and os.path.getsize(p) > 0 for k, p in paths.items()}

    for fp in files:
        fname = os.path.basename(fp)
        if fname in state["completed_files"]:
            continue

        resume_chunks = state["current_file_chunks_done"] if state["current_file"] == fname else 0
        if state["current_file"] != fname:
            state["current_file"] = fname
            state["current_file_chunks_done"] = 0
            resume_chunks = 0
            save_progress(state)

        log(f"Reading {fname} ... (resuming from chunk {resume_chunks})" if resume_chunks
            else f"Reading {fname} ...")

        skiprows = range(1, resume_chunks * CHUNK_SIZE + 1) if resume_chunks else None
        reader = pd.read_csv(fp, dtype=str, chunksize=CHUNK_SIZE, low_memory=False, skiprows=skiprows)

        for local_i, chunk in enumerate(reader):
            chunk_i = resume_chunks + local_i
            cleaned = clean_chunk(chunk, seen_hashes, state["counters"])
            if cleaned is not None and not cleaned.empty:
                for lbl, n in cleaned["Label"].value_counts().items():
                    state["label_counts_all"][lbl] = state["label_counts_all"].get(lbl, 0) + int(n)

                draw = rng.random(len(cleaned))
                split = np.where(draw < 0.70, "train", np.where(draw < 0.85, "val", "test"))
                for name in ("train", "val", "test"):
                    part = cleaned.loc[split == name]
                    if part.empty:
                        continue
                    part.to_csv(paths[name], mode="a", index=False, header=not wrote_header[name])
                    wrote_header[name] = True

            state["current_file_chunks_done"] = chunk_i + 1
            save_progress(state)
            log(f"  chunk {chunk_i + 1} ({len(chunk):,} raw rows) -> running total clean rows: "
                f"{state['counters']['clean_rows']:,} [checkpointed]")

        state["per_file_clean_rows"][fname] = state["counters"]["clean_rows"] - sum(
            v for k, v in state["per_file_clean_rows"].items()
        )
        state["completed_files"].append(fname)
        state["current_file"] = None
        state["current_file_chunks_done"] = 0
        save_progress(state)
        log(f"  -> done with {fname}")

    record(
        "stream_clean_and_split",
        raw_rows_seen=state["counters"]["raw_rows"],
        header_rows_dropped=state["counters"]["header_rows_dropped"],
        nonfinite_speed_rows_dropped=state["counters"]["nonfinite_speed_dropped"],
        other_nan_rows_dropped=state["counters"]["other_nan_dropped"],
        duplicate_rows_dropped=state["counters"]["duplicates_dropped"],
        clean_rows_kept=state["counters"]["clean_rows"],
        per_file_clean_rows=state["per_file_clean_rows"],
        label_distribution_all_clean_data=state["label_counts_all"],
    )
    log(f"Raw rows seen: {state['counters']['raw_rows']:,}  ->  clean rows kept: {state['counters']['clean_rows']:,}")
    return paths


def drop_constant_and_correlated(train_df):
    feature_cols = [c for c in train_df.columns if c != "Label"]

    constant_cols = [c for c in feature_cols if train_df[c].nunique(dropna=False) <= 1]
    feature_cols = [c for c in feature_cols if c not in constant_cols]

    corr = train_df[feature_cols].corr().abs()
    to_drop = set()
    dropped_pairs = []
    for i, a in enumerate(feature_cols):
        if a in to_drop:
            continue
        for b in feature_cols[i + 1:]:
            if b in to_drop:
                continue
            if corr.loc[a, b] >= CORR_THRESHOLD:
                to_drop.add(b)  # keep the earlier (simpler-named) column
                dropped_pairs.append({"kept": a, "dropped": b, "corr": round(float(corr.loc[a, b]), 4)})

    record(
        "constant_and_correlated_columns",
        constant_columns_dropped=constant_cols,
        correlated_pairs_dropped=dropped_pairs,
        correlation_threshold=CORR_THRESHOLD,
    )
    drop_all = constant_cols + list(to_drop)
    log(f"Dropping {len(constant_cols)} constant columns and {len(to_drop)} correlated columns")
    return drop_all


def main():
    stream_paths = stream_clean_and_split()

    log("Loading cleaned train split into memory for scaling/correlation/imbalance ...")
    train_df = pd.read_csv(stream_paths["train"])
    val_df = pd.read_csv(stream_paths["val"])
    test_df = pd.read_csv(stream_paths["test"])
    log(f"train={len(train_df):,}  val={len(val_df):,}  test={len(test_df):,}")

    # label encode on the union of labels seen anywhere, so val/test never hit an unknown code
    all_labels = sorted(set(train_df["Label"]) | set(val_df["Label"]) | set(test_df["Label"]))
    le = LabelEncoder().fit(all_labels)
    label_map = {lbl: int(code) for lbl, code in zip(le.classes_, le.transform(le.classes_))}

    drop_cols = drop_constant_and_correlated(train_df)
    feature_cols = [c for c in train_df.columns if c != "Label" and c not in drop_cols]

    for df in (train_df, val_df, test_df):
        df.drop(columns=[c for c in drop_cols if c in df.columns], inplace=True, errors="ignore")

    # drop attack classes with too few TRAIN rows (say which, per Ch1 1.6.3)
    train_label_counts = train_df["Label"].value_counts()
    rare = train_label_counts[train_label_counts < RARE_CLASS_MIN_TRAIN_ROWS].index.tolist()
    if rare:
        log(f"Dropping rare classes from ALL splits (train support < {RARE_CLASS_MIN_TRAIN_ROWS}): {rare}")
    train_df = train_df[~train_df["Label"].isin(rare)]
    val_df = val_df[~val_df["Label"].isin(rare)]
    test_df = test_df[~test_df["Label"].isin(rare)]
    record("rare_class_removal", dropped_classes=rare, min_train_rows=RARE_CLASS_MIN_TRAIN_ROWS)

    y_train = train_df["Label"].map(label_map).values
    y_val = val_df["Label"].map(label_map).values
    y_test = test_df["Label"].map(label_map).values
    X_train = train_df[feature_cols].values.astype("float32")
    X_val = val_df[feature_cols].values.astype("float32")
    X_test = test_df[feature_cols].values.astype("float32")

    scaler = StandardScaler().fit(X_train)
    X_train = scaler.transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    log("Class distribution BEFORE imbalance handling (train only):")
    before_counts = pd.Series(y_train).value_counts().to_dict()
    log(str(before_counts))

    benign_code = label_map.get("Benign")
    minority_codes = [c for c in np.unique(y_train) if c != benign_code]
    if minority_codes and benign_code is not None:
        target_benign = int(min(
            (train_label_counts.drop(labels=rare, errors="ignore").drop(labels=["Benign"], errors="ignore").max() or 1) * 10,
            (y_train == benign_code).sum(),
        ))
        under = RandomUnderSampler(
            sampling_strategy={benign_code: max(target_benign, 1)}, random_state=SEED
        )
        X_train, y_train = under.fit_resample(X_train, y_train)

        # SMOTE target per minority class: grow it, but nowhere near parity with
        # Benign - equalizing e.g. a 63-row class up to millions is both
        # meaningless (near-duplicate synthetic noise) and computationally
        # infeasible (this is what hung for 15+ minutes before this fix).
        counts_after_under = pd.Series(y_train).value_counts()
        smote_targets = {}
        for code, count in counts_after_under.items():
            if code == benign_code:
                continue
            target = min(count * SMOTE_GROWTH_MULTIPLIER, SMOTE_TARGET_CAP)
            if target > count:
                smote_targets[code] = int(target)

        if smote_targets:
            min_class_size = int(counts_after_under.min())
            smote_k = max(1, min(5, min_class_size - 1))
            try:
                smote = SMOTE(random_state=SEED, k_neighbors=smote_k, sampling_strategy=smote_targets)
                X_train, y_train = smote.fit_resample(X_train, y_train)
            except ValueError as e:
                log(f"SMOTE skipped ({e}); keeping undersampled train set as-is")

    after_counts = pd.Series(y_train).value_counts().to_dict()
    log("Class distribution AFTER imbalance handling (train only):")
    log(str(after_counts))
    record(
        "imbalance_handling",
        train_class_counts_before={str(k): int(v) for k, v in before_counts.items()},
        train_class_counts_after={str(k): int(v) for k, v in after_counts.items()},
    )

    np.savez_compressed(
        os.path.join(OUT_DIR, "train.npz"), X=X_train.astype("float32"), y=y_train.astype("int32")
    )
    np.savez_compressed(
        os.path.join(OUT_DIR, "val.npz"), X=X_val.astype("float32"), y=y_val.astype("int32")
    )
    np.savez_compressed(
        os.path.join(OUT_DIR, "test.npz"), X=X_test.astype("float32"), y=y_test.astype("int32")
    )
    joblib.dump(scaler, os.path.join(OUT_DIR, "scaler.joblib"))
    with open(os.path.join(OUT_DIR, "feature_columns.json"), "w") as f:
        json.dump(feature_cols, f, indent=2)
    with open(os.path.join(OUT_DIR, "label_map.json"), "w") as f:
        json.dump(label_map, f, indent=2)

    for p in stream_paths.values():
        try:
            os.remove(p)
        except OSError:
            pass

    record(
        "final_shapes",
        train_shape=list(X_train.shape), val_shape=list(X_val.shape), test_shape=list(X_test.shape),
        n_features=len(feature_cols),
    )
    with open(os.path.join(OUT_DIR, "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    log(f"Done. Wrote train/val/test .npz, scaler.joblib, label_map.json, feature_columns.json, report.json into {OUT_DIR}")
    log(f"Final shapes -> train {X_train.shape}, val {X_val.shape}, test {X_test.shape}")


if __name__ == "__main__":
    main()
