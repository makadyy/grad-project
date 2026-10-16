# Profiler & XAI — Evaluation Rubric (Draft)

Owner: Seif Mohamed. The task mentions “rubric with C6” but does not provide the official C6 wording. The row below is intentionally a placeholder; replace it before final submission.

| Criterion | Weight | Pass evidence | Measurement |
|---|---:|---|---|
| Feature correctness | 25% | 30 features match `session_features.md` | unit tests + hand-calculated fixture |
| Incremental behavior | 15% | batch ingestion and snapshot/restore work | snapshot test |
| Input validation | 10% | missing fields, unsupported source, negative bytes fail clearly | unit tests |
| Robustness | 10% | duplicate IDs ignored; zero-duration features finite | unit tests |
| SHAP integration | 15% | fitted tree model, correct feature order, ranked contributions | smoke test with trained model |
| Explanation quality | 10% | feature name/value/SHAP value and limitations returned | manual review |
| Integration readiness | 10% | Cowrie/portal/DB/Wazuh adapters implement normalized contract | adapter review |
| C6 — official criterion | 5% | **Insert exact official C6 requirement and evidence.** | pending supervisor/course rubric |

## Acceptance checklist
- [ ] `pytest -q` passes.
- [ ] Exactly 30 numeric feature fields plus `session_id` are emitted.
- [ ] Identical input produces identical output; duplicate IDs are ignored.
- [ ] Snapshot/restore test passes.
- [ ] SHAP tested against the actual trained model and saved feature order.
- [ ] Official C6 wording replaces the placeholder.
- [ ] No raw secrets/tokens or unnecessary PII reach the model matrix.
