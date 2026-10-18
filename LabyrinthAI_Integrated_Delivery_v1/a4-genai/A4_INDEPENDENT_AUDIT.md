# A4 Independent Audit — Martina Saeed (GenAI/RAG)

## Final verification

```text
Independent audit: passed
Pytest: 31 passed, 1 skipped
Dry-run target: 300/300 accepted
Replacement failures: 0
```

## Independently checked

- Fixed-seed world-model determinism and JSON hash consistency.
- World reference validation: employees, departments, managers, projects, systems, customers, and vendors.
- Knowledge-base chunk count and unique stable IDs.
- In-memory RAG ingestion, kind-filtered retrieval, and email prompt grounding.
- Deterministic DB generation and all generated DB batches through the quality gate.
- Foreign-key rejection and invalid DB type rejection.
- Boolean rejection in integer and numeric columns.
- Non-finite numeric rejection (`NaN`/`Infinity`).
- Invalid employee-count and small-target handling.
- Resume manifest protection against world/seed/target mismatch.
- Corrupt JSONL and duplicate artifact ID rejection.
- 300-artifact dry-run, unique artifact IDs, target completion, and replacement behavior.

## Finding fixed during this audit

`QualityGate.check_db_batch()` previously accepted Python `bool` values in `numeric` columns because `bool` is a subclass of `int`. The gate now rejects booleans for both `int` and `numeric` columns with `wrong_type`, and a regression test covers the case.

## External checks not completed in this sandbox

- Real Ollama server with `llama3.1:8b` and `nomic-embed-text`.
- Real pgvector/PostgreSQL roundtrip.
- Human review of realism/style for generated text.
- Production confirmation of DB table names, lure content, and A2/A3 artifact fields.
