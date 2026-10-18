# Gatekeeper A1–A4 — Unified Review/Integration Build

This workspace assembles the repaired A1 data pipeline, A2 profiler, A3 maze/RL v0, and A4 GenAI/RAG package. The goal is a reproducible offline test path and explicit contracts—not a claim that the real dataset or external inference/database services have been run.

## Architecture and contracts

- **A1 (offline benchmark):** prepares corrected CSE-CIC-IDS2018 data, reports capture-day class counts, creates train/validation/test plus unseen-day outputs, and trains baseline models. A1 is a flow-level offline benchmark. It is intentionally not fed directly into A2's live session telemetry because those are different data domains; a fusion model would require its own design and validation.
- **A2 (telemetry features):** converts Cowrie, portal, database and Wazuh normalized JSON events into a stable 30-feature session record. Event IDs are required for reliable deduplication. Category aliases are source-scoped.
- **A3 (abstract control):** consumes an explicit adapter of an A2 feature record as a typed initial MazeState and selects exactly one of five actions through a shielded rule policy/Gymnasium environment.
- **A4 (synthetic world/lures):** provides a deterministic fake company, knowledge chunks and generated artifacts. The integration smoke generates 20 artifacts with FakeLLM and passes the world hash and actually generated honey references as scenario context to A3. This is offline plumbing only; it does not run real Ollama/pgvector.

The executable cross-workstream path is `integration/run_smoke.py`. It exercises A2 → feature adapter → A3 policy/environment with A4 world/artifacts as scenario context, and reports whether real A1 artifacts are present. It does not claim a fused A1 runtime model.

Deep boundary-test results and reproducible remaining defects are documented in [`DEEP_TEST_REPORT_AR.md`](DEEP_TEST_REPORT_AR.md). The normal test suite passes, but the deep run found edge cases in empty A1 evaluation partitions, A2 byte-total overflow, A3 reset-state validation, and A4 department-head membership validation; these four edge cases (plus the A3 observation-space boundary and the A4 type checks found in the follow-up) have since been fixed in code; see `DELIVERY_STATUS_AR.md` (update section). Real-data and real-service items remain open.

The subsequent exhaustive/randomized follow-up, including 33,280 A3 transitions and world-model type mutations, is recorded in [`DEEPEST_TEST_REPORT_AR.md`](DEEPEST_TEST_REPORT_AR.md). It found an additional A3 observation-space boundary violation and A4 malformed-type validation gaps.

## Setup and tests

Python 3.10+ is required. From this directory:

```bash
python -m pip install -r requirements-all.txt
python -m pytest -q
```

Run the cross-workstream smoke separately:

```bash
python integration/run_smoke.py
```

Targeted checks:

```bash
python grad-project-main/data-pipeline/adversarial_a1_review.py
python grad-project-main/data-pipeline/a1_trust_test.py
python -m pytest -q grad-project-main/seif_profiler_xai/tests
python -m pytest -q grad-project-main/maze_rl/tests
python -m pytest -q a4-genai
python a4-genai/adversarial_review.py
python a4-genai/world_model.py --check
```

The A1 trust test uses synthetic data. A valid final project sign-off still requires fetching/verifying the corrected Liu 2022 dataset through the team's approved process and running the official pipeline end-to-end. `integration/run_smoke.py` reports A1 as missing real outputs when `data-pipeline/out/` does not contain the complete splits and baseline report.

## External services and known limitations

- Real A4 generation requires locally installed Ollama models `llama3.1:8b` and `nomic-embed-text`; pgvector integration requires a running database and `PG_DSN`. Neither external service was invoked in this offline integration smoke.
- The A4 quality gate is a consistency filter, not a factuality proof or realism/style judge; human review remains necessary.
- A3 is a newly created v0 interpretation because no A3 source files were included. Its state, reward magnitudes, deterministic transitions and shield policy are explicit assumptions in `grad-project-main/maze_rl/README.md` and must be reviewed by the A3 owner.
- A2 session features and A1 flow features remain separate. Do not train/evaluate a combined model until data lineage, feature schema, evaluation split and leakage controls are approved.
- The project archives did not include the official A1 source data or real pipeline output artifacts.
