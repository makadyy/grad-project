# Integration guide — Seif's A2 Profiler & XAI

## Where this belongs
Copy the `seif_profiler_xai/` folder into the root of `makadyy/grad-project`.
Keep it separate from `data-pipeline/`: Abdelrahman's CSE-CIC-IDS2018 flow-level dataset is not the same thing as the project's live Honey Bot session telemetry.

Suggested repository layout:

```text
grad-project/
  data-pipeline/             # A1: CSE-CIC-IDS2018 preparation and baselines
  seif_profiler_xai/         # A2: session features, incremental extractor, SHAP skeleton
```

## Verify locally
From the repository root:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -e "./seif_profiler_xai[dev]"
python -m pytest seif_profiler_xai/tests -q
```

Run the example:

```bash
python -m pip install -e "./seif_profiler_xai"
python -m profiler_xai.feature_extractor seif_profiler_xai/examples/events.jsonl --out session_features.jsonl
```

If Python reports that `profiler_xai.feature_extractor` was imported before module execution, that is a non-fatal CLI warning from package exports; output should still be checked. Do not use example events as real evidence/results.

## Integration contract
1. Build source-specific adapters that map raw Cowrie, portal, database audit, and Wazuh records into `NormalizedEvent`.
2. Preserve stable event IDs so replayed records are deduplicated.
3. Aggregate by `session_id`, then pass the **exact ordered feature list used when fitting the deployed model** to the prediction service.
4. Keep network-flow model features from A1 separate unless the team deliberately designs and validates a fusion layer.
5. Enable SHAP only after a trained compatible tree model is available; run a smoke test against that actual model.
6. Replace the C6 placeholder in `docs/evaluation_rubric.md` with the official criterion wording before submission.

## Git steps
After copying the folder into the repository:

```bash
git add seif_profiler_xai
git commit -m "Add Seif session profiler and XAI skeleton"
git push
```

This bundle does not push changes to GitHub automatically.
