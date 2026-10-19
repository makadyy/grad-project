"""
build_artifacts.py  (A4, Day 6-10)  Produce the artifacts: plan -> generate -> gate -> save.

  python build_artifacts.py --dry-run                      # fake LLM + in-memory store: tests the whole flow in seconds
  python build_artifacts.py --n 300                        # real: Ollama + in-memory store
  python build_artifacts.py --n 300 --pg                   # real: Ollama + pgvector (docker compose up -d first)

Output (folder out/):
  artifacts.jsonl    accepted artifacts, one JSON per line
  rejections.jsonl   every rejected attempt with its reason codes and raw text (use it to tune the prompts)
  report.json        counts, first-try pass rate, rejection reasons, seconds per artifact

Safe to stop and restart: artifact ids already in artifacts.jsonl are skipped (resume).
"""
import argparse
import collections
import json
import os
import time

from generators import (HONEY_SALARIES, allowed_names_from_hits, db_batches, gen_db_tables, gen_email,
                        gen_memo, plan_artifacts)
from knowledge_base import load_world
from quality_gate import QualityGate
from rag_pipeline import RAG, FakeLLM, InMemoryStore, OllamaClient, PgVectorStore


def read_ids(path):
    ids = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if line.strip():
                    try:
                        obj = json.loads(line)
                        artifact_id = obj["artifact_id"]
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        raise ValueError(f"invalid artifact JSON at {path}:{line_no}") from e
                    if artifact_id in ids:
                        raise ValueError(f"duplicate artifact_id {artifact_id!r} at {path}:{line_no}")
                    ids.add(artifact_id)
    return ids


def append(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_artifacts(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(world, rag, n_total=300, out_dir="out", seed=42, max_attempts=3, log=print):
    os.makedirs(out_dir, exist_ok=True)
    art_path, rej_path = os.path.join(out_dir, "artifacts.jsonl"), os.path.join(out_dir, "rejections.jsonl")
    specs = plan_artifacts(world, n_total, seed)
    dbplan = next(s for s in specs if s["type"] == "_dbplan")
    specs = [s for s in specs if s["type"] != "_dbplan"]
    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest = {"world_sha": world["meta"]["content_sha256"], "seed": seed,
                "n_total": n_total, "schema_version": world["meta"].get("schema_version")}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            existing_manifest = json.load(f)
        if existing_manifest != manifest:
            raise ValueError("output manifest does not match world, seed, or target; use a new output directory")
    elif os.path.exists(art_path) or os.path.exists(rej_path):
        raise ValueError("existing output has no manifest; refusing unsafe resume")
    else:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
    gate = QualityGate(world)
    done = read_ids(art_path)
    # re-register already accepted text with the gate so duplicates across restarts are still caught
    if done:
        with open(art_path, encoding="utf-8") as f:
            for line in f:
                a = json.loads(line)
                if a["type"] in ("email", "memo"):
                    gate.check_text(a["type"], f"Subject: {a['subject']}\n\n{a['body']}",
                                    {"full_name": a["from"].split(" <")[0]}, None, register=True)
                else:
                    gate.check_db_batch(a["table"], a["rows"], _tables_schema(world))
    stats = {"accepted": 0, "first_try": 0, "failed": [], "replacements": 0,
             "replacement_failures": [], "reasons": collections.Counter(), "seconds": 0.0,
             "by_type": collections.Counter()}
    t_start = time.time()

    # ---- text artifacts
    for spec in specs:
        if spec["artifact_id"] in done:
            continue
        accepted = False
        for attempt in range(1, max_attempts + 1):
            if spec["type"] == "email":
                raw, art, s, r, hits = gen_email(rag, world, spec, attempt)
                res = gate.check_text("email", raw, s, r, allowed_names_from_hits(world, hits))
            else:
                raw, art, s, hits = gen_memo(rag, world, spec, attempt)
                res = gate.check_text("memo", raw, s, None, allowed_names_from_hits(world, hits))
            if res.ok:
                art["meta"]["gate"] = "v1"
                append(art_path, art)
                stats["accepted"] += 1
                stats["by_type"][spec["type"]] += 1
                stats["first_try"] += attempt == 1
                accepted = True
                break
            stats["reasons"].update(res.reasons)
            append(rej_path, {"artifact_id": spec["artifact_id"], "attempt": attempt, "reasons": res.reasons,
                              "warnings": res.warnings, "raw": raw})
        if not accepted:
            stats["failed"].append(spec["artifact_id"])
        log(f"{spec['artifact_id']} {'OK ' if accepted else 'FAIL'} ({stats['accepted']} accepted)")

    # A failed text spec must not permanently reduce the requested artifact count.
    # Near-duplicate rejection is expected with a small deterministic FakeLLM sentence
    # pool and can also happen with a real model. Generate deterministic replacement
    # specs of the same type, with fresh ids/seeds, until the text target is restored
    # or a bounded number of replacement attempts is exhausted.
    failed_text = [s for s in specs if s["artifact_id"] in set(stats["failed"])]
    text_target = len(specs)
    existing_text_count = sum(1 for a in _read_artifacts(art_path) if a.get("type") in ("email", "memo"))
    replacement_index = 0
    for original in failed_text:
        for _ in range(max_attempts * 2):
            if sum(1 for a in _read_artifacts(art_path) if a.get("type") in ("email", "memo")) >= text_target:
                break
            replacement_index += 1
            replacement = dict(original)
            replacement["artifact_id"] = f"replacement-{original['type']}-{replacement_index:04d}"
            # Stable IDs may already exist after an interrupted run; never overwrite or duplicate them.
            while replacement["artifact_id"] in read_ids(art_path):
                replacement_index += 1
                replacement["artifact_id"] = f"replacement-{original['type']}-{replacement_index:04d}"
            replacement["seed"] = int(original.get("seed", seed)) + 1000003 * replacement_index
            accepted = False
            for attempt in range(1, max_attempts + 1):
                if replacement["type"] == "email":
                    raw, art, s, r, hits = gen_email(rag, world, replacement, attempt)
                    res = gate.check_text("email", raw, s, r, allowed_names_from_hits(world, hits))
                else:
                    raw, art, s, hits = gen_memo(rag, world, replacement, attempt)
                    res = gate.check_text("memo", raw, s, None, allowed_names_from_hits(world, hits))
                if res.ok:
                    art["meta"]["gate"] = "v1"
                    art["meta"]["replacement_for"] = original["artifact_id"]
                    append(art_path, art)
                    stats["accepted"] += 1
                    stats["replacements"] += 1
                    stats["by_type"][replacement["type"]] += 1
                    accepted = True
                    break
                stats["reasons"].update(res.reasons)
                append(rej_path, {"artifact_id": replacement["artifact_id"], "attempt": attempt,
                                  "reasons": res.reasons, "warnings": res.warnings, "raw": raw,
                                  "replacement_for": original["artifact_id"]})
            if accepted:
                stats["failed"].remove(original["artifact_id"])
                break
        if not accepted:
            stats["replacement_failures"].append(original["artifact_id"])

    # ---- DB batches
    n_o, n_i = dbplan["orders_batches"] * 10, dbplan["invoices_batches"] * 10
    tables = gen_db_tables(world, n_o, n_i, seed)
    schema = _tables_schema(world)
    ref = {"customer_ids": {c["customer_id"] for c in world["customers"]},
           "employee_ids": {e["employee_id"] for e in world["employees"]},
           "order_ids": {o["order_id"] for o in tables["orders"]}}
    for table, idx, rows in db_batches(tables):
        aid = f"db-{table}-{idx:03d}"
        if aid in done:
            continue
        res = gate.check_db_batch(table, rows, schema, ref)
        if res.ok:
            append(art_path, {"artifact_id": aid, "type": "db_rows", "table": table, "rows": rows,
                              "meta": {"honey": table == "salaries_archive", "gate": "v1"}})
            stats["accepted"] += 1
            stats["by_type"]["db_rows"] += 1
            stats["first_try"] += 1
        else:
            stats["reasons"].update(res.reasons)
            stats["failed"].append(aid)
            append(rej_path, {"artifact_id": aid, "attempt": 1, "reasons": res.reasons})

    stats["seconds"] = round(time.time() - t_start, 1)
    total_now = len(read_ids(art_path))
    report = {"target": n_total, "total_artifacts_on_disk": total_now, "target_met": total_now == n_total,
              "this_run": dict(stats["by_type"]), "replacements": stats["replacements"],
              "accepted_this_run": stats["accepted"], "first_try_pass": stats["first_try"],
              "failed_after_retries": stats["failed"], "replacement_failures": stats["replacement_failures"],
              "rejection_reasons": dict(stats["reasons"].most_common()),
              "seconds": stats["seconds"], "world_sha": world["meta"]["content_sha256"]}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


def _tables_schema(world):
    return {**world["db_tables"], "salaries_archive": HONEY_SALARIES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--world", default="world_model.json")
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true", help="fake LLM + in-memory store (no Ollama needed)")
    ap.add_argument("--pg", action="store_true", help="use pgvector instead of the in-memory store")
    ap.add_argument("--dsn", default="postgresql://labyrinth:labyrinth@localhost:5432/labyrinth")
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default="llama3.1:8b")
    ap.add_argument("--skip-ingest", action="store_true", help="knowledge base already loaded in pgvector")
    a = ap.parse_args()

    world = load_world(a.world)
    llm = FakeLLM() if a.dry_run else OllamaClient(a.host, a.model)
    store = PgVectorStore(a.dsn) if a.pg else InMemoryStore()
    rag = RAG(store, llm)
    if not a.skip_ingest:
        print("ingesting knowledge base ...", rag.ingest(world), "chunks")
    report = run(world, rag, a.n, a.out, a.seed, a.max_attempts)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
