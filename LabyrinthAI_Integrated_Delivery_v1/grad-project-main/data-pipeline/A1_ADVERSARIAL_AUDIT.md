# A1 Abdelrahman — Adversarial Audit

## Scope

This review covered the official Day 1–6 path (`01_prepare_parquet.py`, `02_eda_split.py`, `03_baselines.py`) plus syntax, dependencies, the bundled legacy `build_dataset.py`, and the attached A2 tests.

## Findings fixed

1. **Train-only feature selection leakage:** `02_eda_split.py` previously removed constant columns using the complete non-holdout `rest` set, including future validation/test rows. Constant-column selection now happens after the stratified split using `train` only.
2. **Inflated unseen-day macro-F1:** `03_baselines.py` previously passed only `le.classes_` as metric labels. Classes appearing only in validation/test/unseen-day were silently excluded. Metrics now use the union of training and evaluation labels, giving unseen classes their correct zero contribution when never predicted.
3. **Missing operational documentation:** added `requirements.txt`, this README, and a runnable adversarial test.
4. **Silent float32 mutation:** values outside the float32 range are now rejected and counted in `clean_stats.json` instead of being silently clipped.
5. **Ambiguous holdout selection:** holdout matching now uses exact day equality rather than a prefix match.

## Checks executed

- All Python files compile successfully.
- A2 bundled tests: **6 passed**.
- `adversarial_a1_review.py`: **PASS, FAILURES []**.
- Synthetic checks cover repeated headers, identifier removal, float32 features, non-finite rows, exact duplicates, Attempted relabeling, train-only constant selection, day isolation, exact 70/15/15 sizing, and evaluation-only labels in macro-F1.

## Important limitation

The adversarial test is intentionally tiny and synthetic; it proves pipeline invariants but not the final quality or runtime of the full Liu 2022 dataset.

`build_dataset.py` is a separate legacy alternative. It is not the official Day 1–6 path because it performs a random per-row streaming split rather than the official stratified split plus unseen-day hold-out. Its resume logic also resets the RNG instead of restoring its state, so an interrupted run can assign later rows to different splits than an uninterrupted run. It is documented as legacy rather than silently treated as verified.

## Real-data evidence still required

The team must run the official three-script path on the actual corrected dataset and retain `clean_stats.json`, `eda_classes_per_day.csv`, `DATA_CARD.md`, split outputs, and `baseline_results.json`. This audit does not claim that full-dataset run was completed in this sandbox.

## Additional trust checks

- Re-ran the split pipeline twice on the same synthetic input: output digest matched exactly.
- Ran both Decision Tree and XGBoost baselines on generated synthetic splits: six metric outputs were produced and all scores were within [0, 1].
- The harness is saved as `a1_trust_test.py`.
- The adversarial fixture covers float32 overflow and exact holdout behavior.
