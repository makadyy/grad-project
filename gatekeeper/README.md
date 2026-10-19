# A1 Data Pipeline — Gatekeeper

## Official Day 1–6 path

Run these scripts in order:

```bash
python -m pip install -r requirements.txt
python 01_prepare_parquet.py
python 02_eda_split.py
python 03_baselines.py
python adversarial_a1_review.py
```

The official path produces cleaned per-day Parquet, the EDA/data card, a stratified 70/15/15 split on the non-holdout days, an entire unseen-day hold-out, and Decision Tree/XGBoost baseline metrics.

`02_eda_split.py` fits constant-column removal on the training partition only. `03_baselines.py` includes evaluation-only labels in macro-F1 so unseen classes are not silently omitted from the score.

## Important legacy note

`build_dataset.py` is an older alternative pipeline kept for reference. Do not use it as the Day 1–6 evidence path without a separate review: its streaming split is random per row rather than the official stratified + unseen-day design, and its resume path must preserve RNG state to guarantee identical splits after interruption.

## Evidence check

`adversarial_a1_review.py` uses a tiny synthetic fixture to check header removal, identifier removal, non-finite values, duplicates, attempted relabeling, train-only constant selection, day isolation, exact 70/15/15 sizing, and macro-F1 treatment of evaluation-only classes. It does not replace a run on the real Liu 2022 dataset.

For a second independent check, run `python a1_trust_test.py`; it verifies split reproducibility and runs both baseline models on a synthetic dataset.
