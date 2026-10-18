"""pytest -q   (pgvector test runs only if env PG_DSN is set, e.g. postgresql://labyrinth:labyrinth@localhost:5432/labyrinth)"""
import copy
import json
import os

import pytest

from build_artifacts import read_ids, run
from generators import HONEY_SALARIES, db_batches, gen_db_tables, plan_artifacts
from knowledge_base import build_chunks
from quality_gate import QualityGate, parse_text
from rag_pipeline import RAG, FakeLLM, InMemoryStore, PgVectorStore
from world_model import build_world, validate


@pytest.fixture(scope="module")
def world():
    return build_world()


@pytest.fixture()
def gate(world):
    return QualityGate(world)


def people(world):
    emp = {e["employee_id"]: e for e in world["employees"]}
    s = next(e for e in world["employees"] if e["department"] == "FIN" and not e["is_department_head"])
    return s, emp[s["manager_id"]]


def good_email(s, r, extra=""):
    body = (f"Hi {r['first_name']},\n\nI wanted to follow up on the invoice approval backlog from last week. "
            "Several items are still waiting for sign-off and the month end close is getting closer, so I would "
            "appreciate a quick look at the list when you have a moment. If anything is unclear I am happy to go "
            f"through it together this afternoon. {extra}\n\nBest regards,\n{s['full_name']}")
    return "Subject: Invoice approval backlog\n\n" + body


# ---------------------------------------------------------------- world / knowledge base
def test_world_is_valid_and_deterministic(world):
    assert validate(world) == []
    assert build_world()["meta"]["content_sha256"] == world["meta"]["content_sha256"]


def test_world_rejects_too_few_employees():
    with pytest.raises(ValueError, match="n_employees must be"):
        build_world(n_employees=8)


def test_projects_belong_to_sensible_departments(world):
    assert {p["name"]: p["department"] for p in world["projects"]}["ERP Upgrade"] == "IT"


def test_chunks_have_unique_ids_and_cover_world(world):
    ch = build_chunks(world)
    ids = [c["chunk_id"] for c in ch]
    assert len(ids) == len(set(ids))
    assert len(ch) == 1 + len(world["departments"]) + len(world["employees"]) + len(world["projects"]) \
        + len(world["systems"]) + len(world["customers"]) + len(world["vendors"])


# ---------------------------------------------------------------- retrieval
def test_in_memory_retrieval_filters_by_kind(world):
    rag = RAG(InMemoryStore(), FakeLLM())
    rag.ingest(world)
    hits = rag.retrieve("ERP Upgrade project", k=3, kinds=["project"])
    assert hits and all(h["kind"] == "project" for h in hits)
    assert "ERP Upgrade" in hits[0]["text"]


def test_prompt_contains_only_world_facts(world):
    rag = RAG(InMemoryStore(), FakeLLM())
    rag.ingest(world)
    s, r = people(world)
    prompt, hits = rag.email_prompt(world, s, r, "Invoice approval backlog")
    assert s["email"] in prompt and r["email"] in prompt and len(hits) == 6
    for field in ("{company}", "{context}", "{s_name}", "{r_email}", "{topic}", "{tone}"):
        assert field not in prompt  # no unfilled template fields


@pytest.mark.skipif(not os.environ.get("PG_DSN"), reason="set PG_DSN to test pgvector")
def test_pgvector_roundtrip(world):
    store = PgVectorStore(os.environ["PG_DSN"])
    rag = RAG(store, FakeLLM())
    n = rag.ingest(world)
    assert store.count() >= n
    rag.ingest(world)  # idempotent
    assert store.count() == n or store.count() >= n
    hits = rag.retrieve("ERP Upgrade project", k=3, kinds=["project"])
    assert hits and all(h["kind"] == "project" for h in hits)


# ---------------------------------------------------------------- gate: text
def test_good_email_passes(world, gate):
    s, r = people(world)
    res = gate.check_text("email", good_email(s, r), s, r)
    assert res.ok, res.reasons


@pytest.mark.parametrize("mutate,reason", [
    (lambda t, s, r: t.replace("Subject: ", "Re: "), "no_subject_line"),
    (lambda t, s, r: t + "\nPS call [Your Name]", "placeholder"),
    (lambda t, s, r: t.replace("backlog from last week", "backlog (as an AI I cannot)"), "meta_phrase"),
    (lambda t, s, r: t + " Write to ghost@evil.com.", "unknown_email"),
    (lambda t, s, r: t.replace(f"Best regards,\n{s['full_name']}", "Best regards,\nJohn Smith"), "wrong_signoff_name"),
    (lambda t, s, r: t.replace("last week", "on 2030-03-01"), "future_date"),
    (lambda t, s, r: t.replace("last week", "last week. Please also loop in Michael Brown"), "invented_person_name"),
    (lambda t, s, r: t.replace("Hi " + r["first_name"], "Hello team"), "no_greeting_to_recipient"),
    (lambda t, s, r: t + " The password: hunter2", "secret_in_text"),
    (lambda t, s, r: t.split("Best regards")[0], "no_signoff"),
    (lambda t, s, r: "Subject: Invoice approval backlog\n\nHi " + r["first_name"] + ", short.", "too_short"),
])
def test_email_rejections(world, gate, mutate, reason):
    s, r = people(world)
    res = gate.check_text("email", mutate(good_email(s, r), s, r), s, r)
    assert not res.ok and reason in res.reasons, res.reasons


def test_other_employee_name_rejected_unless_allowed(world, gate):
    s, r = people(world)
    other = next(e for e in world["employees"] if e["employee_id"] not in (s["employee_id"], r["employee_id"]))
    txt = good_email(s, r, extra=f"Please copy {other['full_name']} as well.")
    assert "mentions_unlisted_employee" in gate.check_text("email", txt, s, r, register=False).reasons
    assert gate.check_text("email", txt, s, r, allowed_names={other["full_name"]}, register=False).ok


def test_near_duplicate_rejected(world, gate):
    s, r = people(world)
    assert gate.check_text("email", good_email(s, r), s, r).ok
    assert "near_duplicate" in gate.check_text("email", good_email(s, r), s, r).reasons


def test_memo_needs_sender_signoff(world, gate):
    s, _ = people(world)
    body = " ".join(["Please note the updated procedure that starts next month and applies to every team."] * 8)
    ok = f"Subject: Updated expense claim procedure\n\nDear colleagues,\n\n{body}\n\n{s['full_name']}"
    assert gate.check_text("memo", ok, s, register=False).ok
    bad = ok.replace(s["full_name"], "Management")
    assert "memo_missing_sender_signoff" in gate.check_text("memo", bad, s, register=False).reasons


def test_parse_text():
    assert parse_text("Subject: Hi there\n\nBody") == ("Hi there", "Body")
    assert parse_text("Body only")[0] is None


def test_read_ids_rejects_corrupt_or_duplicate_jsonl(tmp_path):
    p = tmp_path / "artifacts.jsonl"
    p.write_text('{"artifact_id":"a"}\n{"artifact_id":"a"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate artifact_id"):
        read_ids(str(p))
    p.write_text('{not-json}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid artifact JSON"):
        read_ids(str(p))


# ---------------------------------------------------------------- DB rows
def test_db_tables_follow_schema_and_integrity(world):
    t = gen_db_tables(world, 100, 80)
    g = QualityGate(world)
    schema = {**world["db_tables"], "salaries_archive": HONEY_SALARIES}
    ref = {"customer_ids": {c["customer_id"] for c in world["customers"]},
           "employee_ids": {e["employee_id"] for e in world["employees"]},
           "order_ids": {o["order_id"] for o in t["orders"]}}
    for table, _, rows in db_batches(t):
        res = g.check_db_batch(table, rows, schema, ref)
        assert res.ok, (table, res.reasons)
    assert gen_db_tables(world, 100, 80) == t  # deterministic


def test_db_gate_catches_broken_rows(world):
    t = gen_db_tables(world, 20, 10)
    schema = world["db_tables"]
    ref = {"customer_ids": {c["customer_id"] for c in world["customers"]}, "order_ids": {o["order_id"] for o in t["orders"]}}
    g = QualityGate(world)
    rows = copy.deepcopy(t["orders"][:10])
    rows[0]["customer_id"] = 99999
    assert "fk_customer" in g.check_db_batch("orders", rows, schema, ref).reasons
    rows = copy.deepcopy(t["orders"][:10])
    rows[1]["order_date"] = "2031-01-01"
    assert "future_date" in g.check_db_batch("orders", rows, schema, ref).reasons
    rows = copy.deepcopy(t["orders"][:10])
    rows[2]["total_amount"] = "12"
    assert "wrong_type" in g.check_db_batch("orders", rows, schema, ref).reasons
    inv = copy.deepcopy(t["invoices"][:10])
    inv[0]["due"] = "2020-01-01"
    assert "due_before_issued" in g.check_db_batch("invoices", inv, schema, ref).reasons
    rows = copy.deepcopy(t["orders"][:10])
    assert g.check_db_batch("orders", rows, schema, ref).ok
    assert "duplicate_primary_key" in g.check_db_batch("orders", rows, schema, ref).reasons


def test_db_gate_rejects_bool_as_numeric(world):
    tables = gen_db_tables(world, 2, 1)
    schema = {**world["db_tables"], "salaries_archive": HONEY_SALARIES}
    ref = {"customer_ids": {c["customer_id"] for c in world["customers"]},
           "order_ids": {o["order_id"] for o in tables["orders"]}}
    row = copy.deepcopy(tables["orders"][0])
    row["total_amount"] = True
    result = QualityGate(world).check_db_batch("orders", [row], schema, ref, register=False)
    assert not result.ok and "wrong_type" in result.reasons


def test_db_gate_rejects_nonfinite_numeric(world):
    tables = gen_db_tables(world, 2, 1)
    schema = {**world["db_tables"], "salaries_archive": HONEY_SALARIES}
    ref = {"customer_ids": {c["customer_id"] for c in world["customers"]}, "order_ids": {o["order_id"] for o in tables["orders"]}}
    row = copy.deepcopy(tables["orders"][0])
    row["total_amount"] = float("nan")
    result = QualityGate(world).check_db_batch("orders", [row], schema, ref, register=False)
    assert not result.ok and "wrong_type" in result.reasons


# ---------------------------------------------------------------- planning + end to end
def test_plan_is_deterministic_and_sums_to_target(world):
    a, b = plan_artifacts(world, 300), plan_artifacts(world, 300)
    assert a == b
    texts = [s for s in a if s["type"] in ("email", "memo")]
    plan = next(s for s in a if s["type"] == "_dbplan")
    assert len(texts) + plan["n_db"] == 300
    assert plan["orders_batches"] > plan["invoices_batches"] >= 0
    assert 9 + plan["orders_batches"] + plan["invoices_batches"] == plan["n_db"]
    assert sum(1 for s in texts if s.get("honey_id") == "H04") == 1
    assert all(s["sender_id"] != s.get("recipient_id") for s in texts)


def test_small_plan_is_exact_or_rejected(world):
    with pytest.raises(ValueError, match="n_total must be"):
        plan_artifacts(world, 6)
    plan = plan_artifacts(world, 10)
    db = next(s for s in plan if s["type"] == "_dbplan")
    assert len([s for s in plan if s["type"] in ("email", "memo")]) + db["n_db"] == 10


def test_end_to_end_dry_run_and_resume(world, tmp_path):
    rag = RAG(InMemoryStore(), FakeLLM())
    rag.ingest(world)
    out = str(tmp_path / "out")
    rep = run(world, rag, n_total=60, out_dir=out, log=lambda *_: None)
    assert rep["total_artifacts_on_disk"] >= 55  # a few fake-LLM duplicates may be rejected
    lines = open(os.path.join(out, "artifacts.jsonl")).read().splitlines()
    ids = [json.loads(l)["artifact_id"] for l in lines]
    assert len(ids) == len(set(ids))
    rep2 = run(world, rag, n_total=60, out_dir=out, log=lambda *_: None)  # resume: nothing duplicated
    ids2 = [json.loads(l)["artifact_id"] for l in open(os.path.join(out, "artifacts.jsonl")).read().splitlines()]
    assert len(ids2) == len(set(ids2))
    assert rep2["total_artifacts_on_disk"] >= rep["total_artifacts_on_disk"]
    assert os.path.exists(os.path.join(out, "report.json"))


def test_dry_run_replaces_failed_text_specs_to_hit_300(world, tmp_path):
    rag = RAG(InMemoryStore(), FakeLLM())
    rag.ingest(world)
    out = str(tmp_path / "out300")
    rep = run(world, rag, n_total=300, out_dir=out, log=lambda *_: None)
    assert rep["target_met"] is True
    assert rep["total_artifacts_on_disk"] == 300
    assert rep["replacement_failures"] == []


def _refresh_hash(w):
    import hashlib, json
    w["meta"]["content_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in w.items() if k != "meta"}, sort_keys=True).encode()).hexdigest()


def test_world_validate_rejects_structural_and_type_mutations():
    import copy, json, os
    from world_model import validate
    base = json.load(open(os.path.join(os.path.dirname(__file__), "world_model.json"), encoding="utf-8"))
    assert validate(base) == []
    muts = {
        "head_other_dept": lambda w: w["departments"][0].__setitem__("head_id", w["departments"][1]["head_id"]),
        "dup_membership": lambda w: w["departments"][0]["member_ids"].append(w["departments"][0]["member_ids"][0]),
        "title_type": lambda w: w["employees"][3].__setitem__("title", 5),
        "email_type": lambda w: w["employees"][3].__setitem__("email", 5),
    }
    for name, fn in muts.items():
        w = copy.deepcopy(base); fn(w); _refresh_hash(w)
        assert validate(w), name
