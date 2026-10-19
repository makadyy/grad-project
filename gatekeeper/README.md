# A1 Data Pipeline — Gatekeeper

## Official Day 1–6 path

Run these scripts in order:

```bash
python -m pip install -r requirements.txt
python 01_prepare_parquet.py
python 02_eda_split.py
python 03_baselines.py
```

The official path produces cleaned per-day Parquet, the EDA/data card, a stratified 70/15/15 split on the non-holdout days, an entire unseen-day hold-out, and Decision Tree/XGBoost baseline metrics.

`02_eda_split.py` fits constant-column removal on the training partition only. `03_baselines.py` includes evaluation-only labels in macro-F1 so unseen classes are not silently omitted from the score.

## Important legacy note

`build_dataset.py` is an older alternative pipeline kept for reference. Do not use it as the Day 1–6 evidence path without a separate review: its streaming split is random per row rather than the official stratified + unseen-day design, and its resume path must preserve RNG state to guarantee identical splits after interruption.

