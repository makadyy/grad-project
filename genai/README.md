# A4: GenAI / RAG (Martina)  -  Day 1-6

Goal: 300 fake-but-consistent artifacts (emails, memos, DB rows) for the decoy company by Day 10.

## Files
| File | What it does |
|---|---|
| `world_model.py` / `world_model.json` | The fake company (Faker, seed 42): 48 employees, 9 depts, 8 systems, customers, vendors, projects, 4 honey lures. `--check` = determinism + references. |
| `gen_test.py` | **First generation test** against Ollama (5 checks). Writes `first_generation_test.json`. |
| `knowledge_base.py` | World -> 104 fact chunks (one per employee, project, system ...) for retrieval. |
| `schema.sql` / `docker-compose.yml` | pgvector table `kb_chunks` (768 dims, cosine HNSW index) + a ready Postgres container. |
| `rag_pipeline.py` | Ollama client, `PgVectorStore` / `InMemoryStore`, email + memo **prompt templates**, `RAG.ingest/retrieve`. |
| `generators.py` | Plans who-writes-to-whom (deterministic), email + memo generators, rule-based DB rows. |
| `quality_gate.py` | **Quality gate v1** (see below). |
| `build_artifacts.py` | Runs everything: plan -> generate -> gate -> retry (3x) -> save. Resumable. |
| `test_pipeline.py` | 31 tests. |

## Setup (once)
```
ollama pull llama3.1:8b
ollama pull nomic-embed-text
pip install -r requirements.txt
docker compose up -d          # pgvector on localhost:5432 (skip if you use --dry-run or no --pg)
```

## Run, in this order
```
python world_model.py                 # world_model.json
python gen_test.py                    # Day 1-3 deliverable: expect all [PASS]
pytest -q                             # 25-26 passed
python build_artifacts.py --dry-run   # whole flow with a FAKE llm, seconds. Checks plumbing only.
python build_artifacts.py --n 300 --pg      # real run. Slow (see below). Safe to Ctrl+C and rerun.
```
Real run time: roughly 10-30 s per email/memo on a laptop CPU -> 1-2 hours for ~210 text artifacts
(the 90 DB batches are instant). Run it overnight, or start with `--n 30` to look at quality first.

## What the output means (`out/`)
- `artifacts.jsonl`  accepted artifacts. Email/memo: from, to, date, subject, body, `meta.retrieved` (which facts the LLM saw). DB: `table` + 10 `rows`.
- `rejections.jsonl` every rejected attempt + reason codes + raw LLM text. **Read this first when the pass rate is low**: it tells you which prompt rule the model breaks.
- `report.json`      per-type counts, first-try passes, rejection reasons, ids that failed all 3 attempts.
- `manifest.json`    world hash, seed, schema version, and target; resume refuses mismatched output.

Artifact counts for `--n 300`: 150 emails (1 is the planted honey email H04), 60 memos, 90 DB batches of 10 rows
(customers, employees, vendors, orders, invoices, and the honey table `salaries_archive`).

## Quality gate v1: what it rejects
Emails/memos: missing Subject, too short/long, non-English, placeholders (`[Name]`, `{{x}}`), AI-isms ("as an AI", "the context provided"),
no greeting / wrong sign-off name, e-mail address that is not in the world, an employee named who was not given to the model,
an invented person name (heuristic), dates after 2025-01-15, passwords or card-like numbers, truncated text, near-duplicates of accepted artifacts.
DB rows: wrong columns/types, duplicate primary keys, broken foreign keys (order -> customer, invoice -> order), future dates, negative amounts, due before issued.

**Limits (be honest in the thesis):** the gate checks consistency, not realism or style. The invented-name check is a heuristic
(first-name list), so a rare invented name can slip through, and a legit unusual phrase can be flagged. Review a sample by hand.

## Known open points (ask the team)
- Seif's feature extractor / Malak's maze need to say which fields they want inside artifacts (e.g. DB table names the portal really uses). Edit `world_model.py` `DB_TABLES` and re-run.
- Egyptian names: Faker uses `en_US` names. Say so if the team wants Arabic/Egyptian names.
- Honey items H01-H04: only H03 (table) and H04 (email) are generated; H01/H02 are file lures still to be written.

## Do NOT commit
`*.gguf`, `.ollama/`, `out/` (see `.gitignore`).

`--n` must be at least 10 because the fixed DB baseline produces 9 batches and the plan reserves one text artifact.
