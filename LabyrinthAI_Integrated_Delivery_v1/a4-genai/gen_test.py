"""
gen_test.py  (A4 Martina, Day 1-3)  First generation test.

Checks, in order:
  1. Ollama server is reachable
  2. llama3.1:8b and nomic-embed-text are pulled
  3. Llama generates ONE email grounded in world_model.json (real people, real domain)
  4. The email passes a basic consistency check (sender/recipient exist, no invented domain)
  5. nomic-embed-text returns a vector (expected 768 dims)
Writes first_generation_test.json with the raw outputs + timings.

Only needs the Python standard library.
Run:  python gen_test.py            (Ollama must be running: `ollama serve`)
      python gen_test.py --host http://localhost:11434 --model llama3.1:8b
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request

GEN_MODEL = "llama3.1:8b"
EMB_MODEL = "nomic-embed-text"
EMB_DIM = 768


def call(host, path, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(host + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def build_prompt(world, sender, recipient, topic):
    c = world["company"]
    return (
        f"You write internal emails for the fictional company {c['name']} ({c['industry']}, {c['hq_city']}).\n"
        f"Tone: {c['tone']}.\n\n"
        f"From: {sender['full_name']} <{sender['email']}>, {sender['title']}, {sender['department']}\n"
        f"To: {recipient['full_name']} <{recipient['email']}>, {recipient['title']}\n"
        f"Topic: {topic}\n\n"
        "Write a realistic 80-120 word email body. Use ONLY the two people above. "
        "Do not invent other names, email addresses or company names. "
        "Output the email only, starting with 'Subject:'."
    )


def check_email(text, world, sender, recipient):
    """Return a list of problems; empty means the email is consistent with the world."""
    problems = []
    if not text.strip().lower().startswith("subject:"):
        problems.append("does not start with 'Subject:'")
    words = len(text.split())
    if not 40 <= words <= 220:
        problems.append(f"length {words} words outside 40-220")
    domain = world["company"]["domain"]
    for addr in re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text):
        if not addr.lower().endswith("@" + domain):
            problems.append(f"foreign email address: {addr}")
        elif addr.lower() not in {e["email"].lower() for e in world["employees"]}:
            problems.append(f"unknown employee address: {addr}")
    known = {e["full_name"] for e in world["employees"]}
    allowed = {sender["full_name"], recipient["full_name"], sender["first_name"], recipient["first_name"]}
    for name in known - {sender["full_name"], recipient["full_name"]}:
        if name in text and name not in allowed:
            problems.append(f"mentions other employee: {name}")
    if recipient["first_name"] not in text:
        problems.append("does not address the recipient by name")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:11434")
    ap.add_argument("--model", default=GEN_MODEL)
    ap.add_argument("--embed-model", default=EMB_MODEL)
    ap.add_argument("--world", default="world_model.json")
    ap.add_argument("--out", default="first_generation_test.json")
    a = ap.parse_args()
    report = {"host": a.host, "model": a.model, "embed_model": a.embed_model, "steps": {}}

    def step(name, ok, detail=""):
        report["steps"][name] = {"ok": ok, "detail": detail}
        print(("[PASS] " if ok else "[FAIL] ") + name + (f"  {detail}" if detail else ""))
        return ok

    # 1. server
    try:
        tags = call(a.host, "/api/tags", timeout=10)
    except (urllib.error.URLError, OSError) as e:
        step("ollama reachable", False, f"{e}. Start it with `ollama serve`.")
        sys.exit(1)
    step("ollama reachable", True)

    # 2. models
    have = {m["name"] for m in tags.get("models", [])}
    have_base = {n.split(":")[0] for n in have}
    ok_gen = a.model in have or a.model.split(":")[0] in have_base and ":" not in a.model
    ok_emb = a.embed_model in have or a.embed_model.split(":")[0] in have_base
    step("generation model pulled", ok_gen, "" if ok_gen else f"run: ollama pull {a.model}")
    step("embedding model pulled", ok_emb, "" if ok_emb else f"run: ollama pull {a.embed_model}")
    if not (ok_gen and ok_emb):
        json.dump(report, open(a.out, "w"), indent=2)
        sys.exit(1)

    # 3. generate one email
    world = json.load(open(a.world, encoding="utf-8"))
    emp = {e["employee_id"]: e for e in world["employees"]}
    recipient = next(e for e in world["employees"] if e["department"] == "FIN" and not e["is_department_head"])
    sender = emp[recipient["manager_id"]]
    topic = world["email_topics"][1]
    prompt = build_prompt(world, sender, recipient, topic)
    t0 = time.time()
    try:
        resp = call(a.host, "/api/generate", {
            "model": a.model, "prompt": prompt, "stream": False,
            "options": {"temperature": 0.7, "seed": 42, "num_predict": 300},
        })
    except (urllib.error.URLError, OSError) as e:
        step("generation call", False, str(e))
        sys.exit(1)
    dt = time.time() - t0
    text = resp.get("response", "")
    step("generation call", bool(text.strip()), f"{dt:.1f}s, {len(text.split())} words")
    report["email"] = {"prompt": prompt, "text": text, "seconds": round(dt, 1),
                       "sender": sender["employee_id"], "recipient": recipient["employee_id"]}

    # 4. consistency
    problems = check_email(text, world, sender, recipient)
    step("email consistent with world", not problems, "; ".join(problems))
    report["email"]["problems"] = problems

    # 5. embeddings
    try:
        emb = call(a.host, "/api/embed", {"model": a.embed_model, "input": [text or "test"]})
        vec = emb["embeddings"][0]
        step("embedding works", len(vec) == EMB_DIM, f"{len(vec)} dims (expected {EMB_DIM})")
    except (urllib.error.URLError, OSError, KeyError, IndexError) as e:
        step("embedding works", False, str(e))

    json.dump(report, open(a.out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\nreport written to {a.out}")
    print("\n--- generated email ---\n" + text)
    sys.exit(0 if all(s["ok"] for s in report["steps"].values()) else 1)


if __name__ == "__main__":
    main()
