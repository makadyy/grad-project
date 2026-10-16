# Profiler & XAI — Seif Mohamed (A2, Days 1–6)

For the Honey Bot / Gatekeeper graduation project. This folder contains the A2 deliverables:

- `docs/session_features.md`: 30-feature dictionary and telemetry field mapping.
- `docs/evaluation_rubric.md`: draft acceptance rubric; C6 remains a placeholder until the official wording is supplied.
- `src/profiler_xai/`: normalized event schema, incremental session feature extractor, and optional SHAP tree-explainer service.
- `tests/`: unit tests for validation, aggregation, deduplication, and snapshot/restore.
- `examples/events.jsonl`: synthetic demonstration events only.

## Important architecture boundary
A1's CSE-CIC-IDS2018 data are network-flow records. These A2 features summarize Honey Bot session telemetry (Cowrie, portal, DB audit, Wazuh). They are separate inputs and must not be silently treated as the same columns. A fusion model, if needed, requires an explicit design and validation.

## Install and test
From this folder:

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q
```

Run the example:

```bash
python -m profiler_xai.feature_extractor examples/events.jsonl --out out/session_features.jsonl
```

Optional SHAP dependencies: `python -m pip install -e ".[xai]"`.

The extractor currently accepts **normalized events**, not arbitrary raw log exports. Source-specific adapters are still required. The SHAP skeleton must be smoke-tested with the actual trained XGBoost model and its saved feature order before claiming end-to-end integration.

See `INTEGRATION_GUIDE.md` for repository placement and next integration steps.
