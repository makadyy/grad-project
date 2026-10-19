"""
generate.py  (A4, Day 5-6)  Plans and generates the artifacts.

  plan_artifacts()   deterministic list of specs (who writes to whom about what) - no LLM involved
  gen_email()        RAG prompt -> Llama -> checked by the gate
  gen_memo()         same for memos
  gen_db_tables()    rule-based rows that follow company["db_tables"] (no LLM: foreign keys must be exact)

Why DB rows are rule-based: an order that points to a customer_id that does not exist is an instant tell for an
attacker, and an LLM cannot guarantee referential integrity. Free-text fields can be LLM-filled later.
"""
import random
from datetime import date, datetime, timedelta

TOPIC_DEPTS = {  # topic -> (sender dept, recipient dept); ANY = any department, HEAD = recipient is the dept head
    "Quarterly fleet maintenance schedule": ("OPS", "OPS"),
    "Invoice approval backlog": ("FIN", "FIN"),
    "New hire onboarding checklist": ("HR", "ANY"),
    "Warehouse safety inspection": ("OPS", "LEG"),
    "VPN access renewal": ("IT", "ANY"),
    "Customer contract renewal": ("SAL", "LEG"),
    "Fuel surcharge adjustment": ("FIN", "SAL"),
    "Vendor payment run": ("PRC", "FIN"),
    "Holiday coverage rota": ("HR", "OPS"),
    "Server patch window": ("IT", "ANY"),
    "Budget review for next quarter": ("FIN", "HEAD"),
    "Driver shift changes": ("OPS", "OPS"),
    "Customs documentation update": ("LEG", "OPS"),
    "Mandatory security awareness training": ("SEC", "ANY"),
}
ANGLES = ["asks for a status update", "confirms a decision that was made", "raises a small problem and proposes a fix",
          "requests approval", "shares an upcoming deadline", "thanks the recipient and follows up",
          "asks a clarifying question", "sends a short reminder"]

MEMO_TOPICS = [  # (topic, owner dept, audience)
    ("Office closure for the public holiday", "HR", "all staff"),
    ("Reminder to complete the security awareness training", "SEC", "all staff"),
    ("Planned maintenance window for the file server", "IT", "all staff"),
    ("Updated expense claim procedure", "FIN", "all staff"),
    ("Warehouse safety rules after the latest inspection", "OPS", "the Operations department"),
    ("Fleet maintenance schedule for next quarter", "OPS", "the Operations department"),
    ("New vendor onboarding process", "PRC", "all staff"),
    ("Contract review turnaround times", "LEG", "the Sales and Procurement departments"),
    ("Customer account review cycle", "SAL", "the Sales department"),
    ("Annual leave requests for the coming quarter", "HR", "all staff"),
    ("Password and VPN access reminder", "IT", "all staff"),
    ("Recruitment drive for drivers", "HR", "the Operations department"),
]
MEMO_ANGLES = ["announces the change and its start date", "reminds staff and explains why it matters",
               "summarises what happens next and who to contact"]

HONEY_SALARIES = {"employee_id": "text", "full_name": "text", "salary_egp": "int", "band": "text", "last_review": "date"}
DEPOTS = ["Cairo", "Alexandria", "Suez", "Port Said", "Giza"]


# ----------------------------------------------------------------------------------------------- planning
def _work_datetime(rng, anchor, max_days=75):
    for _ in range(50):
        d = anchor - timedelta(days=rng.randint(1, max_days))
        if d.weekday() not in (4, 5):  # Egypt: Friday and Saturday are the weekend
            return datetime(d.year, d.month, d.day, rng.randint(8, 17), rng.choice([0, 7, 15, 22, 31, 40, 48, 55]))
    return datetime(anchor.year, anchor.month, anchor.day, 9, 0)


def plan_artifacts(world, n_total=300, seed=42, share_memo=0.2, share_db=0.3):
    min_db_batches = 9  # customers, employees, vendors, and the honey table
    if n_total < min_db_batches + 1:
        raise ValueError(f"n_total must be >= {min_db_batches + 1} to include the fixed DB batches and one text artifact")
    anchor = date.fromisoformat(world["meta"]["anchor_date"])
    emps = world["employees"]
    by_dept, heads = {}, {}
    for e in emps:
        by_dept.setdefault(e["department"], []).append(e)
        if e["is_department_head"]:
            heads[e["department"]] = e
    ceo = next(e for e in emps if e["manager_id"] is None)
    n_db = max(min_db_batches, round(n_total * share_db))
    n_text = n_total - n_db
    n_memo = min(round(n_total * share_memo), n_text)
    n_email = n_text - n_memo
    specs = []

    # emails
    for i in range(n_email):
        rng = random.Random(f"{seed}-email-{i}")
        if i == 0:  # the planted honey email (world["honey"] H04)
            h = next(h for h in world["honey"] if h["honey_id"] == "H04")
            sender, recipient = heads["FIN"], ceo
            topic, angle = "Wire transfer approval - urgent", "asks for urgent approval of a large wire transfer to a vendor"
            honey_id = h["honey_id"]
        else:
            topic = list(TOPIC_DEPTS)[i % len(TOPIC_DEPTS)]
            angle = ANGLES[(i // len(TOPIC_DEPTS)) % len(ANGLES)]
            sd, rd = TOPIC_DEPTS[topic]
            sender = rng.choice(by_dept[sd])
            if rd == "ANY":
                pool = emps
            elif rd == "HEAD":
                pool = [heads[sender["department"]]] if heads[sender["department"]] is not sender else [ceo]
            else:
                pool = by_dept[rd]
            pool = [e for e in pool if e["employee_id"] != sender["employee_id"]]
            recipient = rng.choice(pool)
            honey_id = None
        specs.append({"artifact_id": f"email-{i + 1:04d}", "type": "email", "topic": topic, "angle": angle,
                      "sender_id": sender["employee_id"], "recipient_id": recipient["employee_id"],
                      "sent_at": _work_datetime(rng, anchor).isoformat(), "seed": rng.randint(1, 10**6),
                      "honey_id": honey_id})

    # memos
    projects = world["projects"]
    memo_bases = [(t, d, a) for t, d, a in MEMO_TOPICS] + [
        (f"Status update on the {p['name']} project", p["department"], "all staff") for p in projects]
    for i in range(n_memo):
        rng = random.Random(f"{seed}-memo-{i}")
        topic, dept, audience = memo_bases[i % len(memo_bases)]
        angle = MEMO_ANGLES[(i // len(memo_bases)) % len(MEMO_ANGLES)]
        sender = heads[dept] if rng.random() < 0.8 else ceo
        specs.append({"artifact_id": f"memo-{i + 1:04d}", "type": "memo", "topic": topic, "angle": angle,
                      "audience": audience, "sender_id": sender["employee_id"],
                      "sent_at": _work_datetime(rng, anchor).isoformat(), "seed": rng.randint(1, 10**6)})

    # DB batches: 8 fixed (customers/employees/vendors) + 1 honey + split of the rest between orders and invoices
    rest = n_db - min_db_batches
    k_o = -(-rest * 10 // 18)        # ceil(rest / 1.8): orders get a bit more than half
    k_i = rest - k_o                # invoices (always fewer than orders)
    specs.append({"artifact_id": "dbplan", "type": "_dbplan", "orders_batches": k_o, "invoices_batches": k_i,
                  "n_db": n_db})
    return specs


# ----------------------------------------------------------------------------------------------- text
def parse_llm_text(raw):
    from check import parse_text
    return parse_text(raw)


def _emp_map(world):
    return {e["employee_id"]: e for e in world["employees"]}


def gen_email(rag, world, spec, attempt=1):
    emp = _emp_map(world)
    s, r = emp[spec["sender_id"]], emp[spec["recipient_id"]]
    prompt, hits = rag.email_prompt(world, s, r, f"{spec['topic']} (the email {spec['angle']})")
    raw = rag.llm.generate(prompt, seed=spec["seed"] + attempt, temperature=0.7 + 0.05 * (attempt - 1))
    subject, body = parse_llm_text(raw)
    art = {"artifact_id": spec["artifact_id"], "type": "email", "date": spec["sent_at"],
           "from": f"{s['full_name']} <{s['email']}>", "to": f"{r['full_name']} <{r['email']}>",
           "subject": subject, "body": body,
           "meta": {"topic": spec["topic"], "angle": spec["angle"], "sender_id": s["employee_id"],
                    "recipient_id": r["employee_id"], "honey_id": spec.get("honey_id"),
                    "retrieved": [h["chunk_id"] for h in hits], "seed": spec["seed"] + attempt, "attempt": attempt}}
    return raw, art, s, r, hits


def gen_memo(rag, world, spec, attempt=1):
    emp = _emp_map(world)
    s = emp[spec["sender_id"]]
    prompt, hits = rag.memo_prompt(world, s, spec["audience"], f"{spec['topic']} (the memo {spec['angle']})")
    raw = rag.llm.generate(prompt, seed=spec["seed"] + attempt, temperature=0.7 + 0.05 * (attempt - 1), max_tokens=450)
    subject, body = parse_llm_text(raw)
    art = {"artifact_id": spec["artifact_id"], "type": "memo", "date": spec["sent_at"],
           "from": f"{s['full_name']} <{s['email']}>", "to": spec["audience"], "subject": subject, "body": body,
           "meta": {"topic": spec["topic"], "angle": spec["angle"], "sender_id": s["employee_id"],
                    "retrieved": [h["chunk_id"] for h in hits], "seed": spec["seed"] + attempt, "attempt": attempt}}
    return raw, art, s, hits


def allowed_names_from_hits(world, hits):
    """Employee names that the retrieved context mentions - the LLM may legitimately name them."""
    names = {e["full_name"] for e in world["employees"]}
    return {n for n in names if any(n in h["text"] for h in hits)}


# ----------------------------------------------------------------------------------------------- DB rows
def gen_db_tables(world, n_order_rows, n_invoice_rows, seed=42):
    rng = random.Random(f"{seed}-db")
    anchor = date.fromisoformat(world["meta"]["anchor_date"])
    customers = [{k: c[k] for k in world["db_tables"]["customers"]} for c in world["customers"]]
    employees = [{"employee_id": e["employee_id"], "full_name": e["full_name"],
                  "department": e["department"], "title": e["title"], "email": e["email"],
                  "hire_date": e["hire_date"], "salary_band": e["salary_band"]} for e in world["employees"]]
    vendors = [{k: v[k] for k in world["db_tables"]["vendors"]} for v in world["vendors"]]

    start = date(2024, 1, 1)
    days = (anchor - timedelta(days=3) - start).days
    dates = sorted(start + timedelta(days=rng.randint(0, days)) for _ in range(n_order_rows))
    orders = []
    for i, d in enumerate(dates):
        cu = rng.choice(customers)
        depot = rng.choice([x for x in DEPOTS if x != cu["city"]] or DEPOTS)
        invoiceable = i < n_invoice_rows  # oldest orders are the ones already invoiced
        status = rng.choice(["delivered", "invoiced"]) if invoiceable else rng.choice(["pending", "in_transit", "cancelled"])
        orders.append({"order_id": 90001 + i, "customer_id": cu["customer_id"], "order_date": d.isoformat(),
                       "status": status, "total_amount": round(rng.uniform(1500, 90000), 2),
                       "route": f"{depot} -> {cu['city']}"})
    invoices = []
    for j, o in enumerate(orders[:n_invoice_rows]):
        issued = min(anchor, date.fromisoformat(o["order_date"]) + timedelta(days=rng.randint(1, 5)))
        due = issued + timedelta(days=30)
        paid = due < anchor - timedelta(days=rng.randint(0, 20)) and rng.random() < 0.85
        invoices.append({"invoice_id": 40001 + j, "order_id": o["order_id"], "issued": issued.isoformat(),
                         "due": due.isoformat(), "amount": o["total_amount"], "paid": paid})

    # honey table: salaries_archive (fake numbers, flagged in world["honey"] H03)
    band_pay = {"B1": 9000, "B2": 13000, "B3": 19000, "B4": 28000, "B5": 42000}
    honey = [{"employee_id": e["employee_id"], "full_name": e["full_name"],
              "salary_egp": band_pay[e["salary_band"]] + rng.randint(-8, 8) * 250, "band": e["salary_band"],
              "last_review": (anchor - timedelta(days=rng.randint(30, 400))).isoformat()} for e in world["employees"][:10]]
    return {"customers": customers, "employees": employees, "vendors": vendors, "orders": orders,
            "invoices": invoices, "salaries_archive": honey}


def db_batches(tables, size=10):
    out = []
    for name, rows in tables.items():
        for i in range(0, len(rows), size):
            out.append((name, i // size + 1, rows[i:i + size]))
    return out
