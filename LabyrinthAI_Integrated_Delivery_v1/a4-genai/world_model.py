"""
world_model.py  (A4 Martina, Day 1-3)

Builds the fake company ("the world") that every generated artifact
(emails, memos, DB rows) must stay consistent with.

Deterministic: same SEED  ->  byte-identical world_model.json.
No call to datetime.now(); all dates are derived from ANCHOR_DATE.

Run:
    pip install faker
    python world_model.py                 # writes world_model.json
    python world_model.py --seed 7 --employees 60 --out other.json
    python world_model.py --check         # build twice + validate, exit 1 on failure
"""
import argparse
import hashlib
import json
import random
import sys
from datetime import date, timedelta

from faker import Faker

SCHEMA_VERSION = "1.0"
SEED = 42
N_EMPLOYEES = 48
ANCHOR_DATE = date(2025, 1, 15)  # "today" inside the fake world

COMPANY_NAME = "Nilecrest Logistics"
DOMAIN = "nilecrest-logistics.com"

# (code, name, headcount share, job titles; first title = department head)
DEPARTMENTS = [
    ("EXEC", "Executive Office", 0.04, ["Chief Executive Officer", "Chief of Staff"]),
    ("FIN", "Finance", 0.12, ["Finance Director", "Senior Accountant", "Accounts Payable Clerk", "Financial Analyst"]),
    ("HR", "Human Resources", 0.08, ["HR Director", "HR Business Partner", "Recruiter"]),
    ("IT", "Information Technology", 0.14, ["IT Director", "Systems Administrator", "Network Engineer", "Helpdesk Technician", "Database Administrator"]),
    ("OPS", "Operations", 0.26, ["Operations Director", "Fleet Manager", "Dispatch Coordinator", "Warehouse Supervisor", "Logistics Planner"]),
    ("SAL", "Sales", 0.16, ["Sales Director", "Account Manager", "Sales Representative"]),
    ("LEG", "Legal & Compliance", 0.06, ["General Counsel", "Compliance Officer", "Contracts Specialist"]),
    ("PRC", "Procurement", 0.08, ["Procurement Director", "Procurement Specialist", "Vendor Manager"]),
    ("SEC", "Information Security", 0.06, ["Security Manager", "Security Analyst"]),
]

# Sensitivity drives which employees/systems are "interesting" to an attacker.
SYSTEMS = [
    # id, name, kind, owner dept, host, sensitivity
    ("sys-portal", "Employee Portal", "web", "IT", "portal.int.nilecrest-logistics.com", "medium"),
    ("sys-erp", "ERP (Orders & Billing)", "web", "FIN", "erp.int.nilecrest-logistics.com", "high"),
    ("sys-hrms", "HR Management System", "web", "HR", "hrms.int.nilecrest-logistics.com", "high"),
    ("sys-fleet", "Fleet Tracking", "web", "OPS", "fleet.int.nilecrest-logistics.com", "medium"),
    ("sys-files", "File Server", "smb", "IT", "files01.int.nilecrest-logistics.com", "high"),
    ("sys-db", "Primary Database", "postgres", "IT", "db01.int.nilecrest-logistics.com", "critical"),
    ("sys-mail", "Mail Server", "smtp", "IT", "mail.nilecrest-logistics.com", "medium"),
    ("sys-vpn", "VPN Gateway", "vpn", "IT", "vpn.nilecrest-logistics.com", "high"),
]

# Table layouts the DB-row generator must follow (column: type).
DB_TABLES = {
    "customers": {"customer_id": "int", "company": "text", "contact_name": "text", "email": "text",
                  "phone": "text", "city": "text", "credit_limit": "numeric", "account_manager_id": "text"},
    "orders": {"order_id": "int", "customer_id": "int", "order_date": "date", "status": "text",
               "total_amount": "numeric", "route": "text"},
    "invoices": {"invoice_id": "int", "order_id": "int", "issued": "date", "due": "date",
                 "amount": "numeric", "paid": "bool"},
    "employees": {"employee_id": "text", "full_name": "text", "department": "text", "title": "text",
                  "email": "text", "hire_date": "date", "salary_band": "text"},
    "vendors": {"vendor_id": "int", "name": "text", "category": "text", "contact_email": "text",
                "iban_last4": "text"},
}

EMAIL_TOPICS = [
    "Quarterly fleet maintenance schedule", "Invoice approval backlog", "New hire onboarding checklist",
    "Warehouse safety inspection", "VPN access renewal", "Customer contract renewal",
    "Fuel surcharge adjustment", "Vendor payment run", "Holiday coverage rota",
    "Server patch window", "Budget review for next quarter", "Driver shift changes",
    "Customs documentation update", "Mandatory security awareness training",
]

PROJECTS = [  # (name, owning department)
    ("Route Optimisation 2025", "OPS"), ("Warehouse Barcode Migration", "OPS"), ("ERP Upgrade", "IT"),
    ("Driver Mobile App", "IT"), ("Cold-Chain Expansion", "OPS"), ("Vendor Consolidation", "PRC"),
    ("Payroll Automation", "FIN"), ("Disaster Recovery Test", "IT"),
]

SALARY_BANDS = ["B1", "B2", "B3", "B4", "B5"]


def _slug(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum() or c == " ").replace(" ", ".")


def build_world(seed: int = SEED, n_employees: int = N_EMPLOYEES) -> dict:
    """Return the whole world as a plain dict (JSON-serialisable)."""
    if n_employees < len(DEPARTMENTS):
        raise ValueError(f"n_employees must be >= {len(DEPARTMENTS)}")
    rng = random.Random(seed)
    Faker.seed(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)

    def rand_date_between(start: date, end: date) -> date:
        return start + timedelta(days=rng.randint(0, (end - start).days))

    # ---------- employees ----------
    # head count per department (at least 1 head each, total == n_employees)
    counts = {c: max(1, round(n_employees * share)) for c, _, share, _ in DEPARTMENTS}
    diff = n_employees - sum(counts.values())
    order = sorted(counts, key=lambda c: -counts[c])
    i = 0
    while diff != 0:  # fix rounding drift deterministically
        c = order[i % len(order)]
        if diff > 0:
            counts[c] += 1
            diff -= 1
        elif counts[c] > 1:
            counts[c] -= 1
            diff += 1
        i += 1

    employees, used_emails = [], set()
    seq = 1000
    dept_head = {}
    for code, dname, _, titles in DEPARTMENTS:
        for k in range(counts[code]):
            seq += 1
            first, last = fake.first_name(), fake.last_name()
            base = f"{_slug(first)}.{_slug(last)}"
            email, n = f"{base}@{DOMAIN}", 2
            while email in used_emails:
                email = f"{base}{n}@{DOMAIN}"
                n += 1
            used_emails.add(email)
            is_head = k == 0
            title = titles[0] if is_head else titles[1 + (k - 1) % (len(titles) - 1)] if len(titles) > 1 else titles[0]
            emp = {
                "employee_id": f"E{seq}",
                "first_name": first,
                "last_name": last,
                "full_name": f"{first} {last}",
                "email": email,
                "department": code,
                "title": title,
                "is_department_head": is_head,
                "manager_id": None,  # filled below
                "hire_date": rand_date_between(date(2012, 1, 1), date(2024, 12, 1)).isoformat(),
                "salary_band": rng.choice(SALARY_BANDS[3:] if is_head else SALARY_BANDS[:4]),
                "phone": fake.numerify("+20 10########"),
                "username": f"{first[0].lower()}{_slug(last)}"[:16],
                "office": rng.choice(["Cairo HQ", "Cairo HQ", "Alexandria Hub", "Suez Depot"]),
            }
            employees.append(emp)
            if is_head:
                dept_head[code] = emp

    ceo = dept_head["EXEC"]
    for e in employees:
        if e is ceo:
            e["manager_id"] = None
        elif e["is_department_head"]:
            e["manager_id"] = ceo["employee_id"]
        else:
            e["manager_id"] = dept_head[e["department"]]["employee_id"]

    # unique usernames
    seen = {}
    for e in employees:
        u = e["username"]
        if u in seen:
            seen[u] += 1
            e["username"] = f"{u}{seen[u]}"
        else:
            seen[u] = 1

    by_dept = {}
    for e in employees:
        by_dept.setdefault(e["department"], []).append(e)

    # ---------- departments ----------
    departments = [
        {"code": c, "name": n, "head_id": dept_head[c]["employee_id"],
         "member_ids": [e["employee_id"] for e in by_dept[c]]}
        for c, n, _, _ in DEPARTMENTS
    ]

    # ---------- systems (owners point to real employees) ----------
    systems = []
    for sid, name, kind, owner_dept, host, sens in SYSTEMS:
        admin = next((e for e in by_dept["IT"] if "Administrator" in e["title"] or "Engineer" in e["title"]),
                     dept_head["IT"])
        systems.append({"system_id": sid, "name": name, "kind": kind, "owner_department": owner_dept,
                        "host": host, "sensitivity": sens, "admin_id": admin["employee_id"]})

    # ---------- customers / vendors ----------
    sales = by_dept["SAL"]
    customers = []
    for cid in range(1, 21):
        am = rng.choice(sales)
        customers.append({
            "customer_id": 5000 + cid, "company": fake.company(), "contact_name": fake.name(),
            "email": None, "phone": fake.numerify("+20 2 ########"), "city": rng.choice(
                ["Cairo", "Giza", "Alexandria", "Port Said", "Suez", "Mansoura", "Tanta", "Aswan"]),
            "credit_limit": rng.choice([25000, 50000, 100000, 250000]), "account_manager_id": am["employee_id"],
        })
        c = customers[-1]
        c["email"] = f"{_slug(c['contact_name'])}@{_slug(c['company']).replace('.', '')[:20]}.example.com"

    vendors = []
    vcats = ["Fuel", "Tyres", "IT Hardware", "Packaging", "Insurance", "Cleaning", "Software Licences"]
    vm = [e for e in by_dept["PRC"]]
    for vid in range(1, 11):
        v = fake.company()
        vendors.append({"vendor_id": 7000 + vid, "name": v, "category": rng.choice(vcats),
                        "contact_email": f"accounts@{_slug(v).replace('.', '')[:20]}.example.com",
                        "iban_last4": f"{rng.randint(0, 9999):04d}", "owner_id": rng.choice(vm)["employee_id"]})

    # ---------- projects ----------
    projects = []
    for i, (pname, dept) in enumerate(PROJECTS, 1):
        lead = rng.choice(by_dept[dept])
        start = rand_date_between(date(2024, 1, 1), date(2025, 1, 1))
        members = rng.sample([e["employee_id"] for e in employees], k=rng.randint(3, 6))
        if lead["employee_id"] not in members:
            members[0] = lead["employee_id"]
        projects.append({"project_id": f"P{i:02d}", "name": pname, "department": dept,
                         "lead_id": lead["employee_id"], "member_ids": members,
                         "start": start.isoformat(),
                         "status": rng.choice(["planning", "in_progress", "in_progress", "on_hold"])})

    # ---------- honey placeholders (planted lures; content filled by generators) ----------
    honey = [
        {"honey_id": "H01", "kind": "file", "path": "/srv/finance/Payroll_Q4_2024.xlsx",
         "owner_id": dept_head["FIN"]["employee_id"], "lure": "payroll"},
        {"honey_id": "H02", "kind": "file", "path": "/srv/it/vpn_credentials_backup.txt",
         "owner_id": dept_head["IT"]["employee_id"], "lure": "credentials"},
        {"honey_id": "H03", "kind": "db_table", "name": "salaries_archive",
         "owner_id": dept_head["HR"]["employee_id"], "lure": "salary data"},
        {"honey_id": "H04", "kind": "email", "subject": "RE: Wire transfer approval - urgent",
         "owner_id": dept_head["FIN"]["employee_id"], "lure": "finance fraud"},
    ]

    world = {
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "seed": seed,
            "anchor_date": ANCHOR_DATE.isoformat(),
            "generator": "world_model.py",
            "faker_locale": "en_US",
        },
        "company": {
            "name": COMPANY_NAME, "domain": DOMAIN, "industry": "Freight & logistics",
            "founded": 2009, "hq_city": "Cairo", "headcount": len(employees),
            "mission": "Reliable freight and warehousing across Egypt and the Red Sea corridor.",
            "tone": "professional, concise, mildly formal; sign-off 'Best regards'",
        },
        "departments": departments,
        "employees": employees,
        "systems": systems,
        "customers": customers,
        "vendors": vendors,
        "projects": projects,
        "email_topics": EMAIL_TOPICS,
        "db_tables": DB_TABLES,
        "honey": honey,
    }
    world["meta"]["content_sha256"] = hashlib.sha256(
        json.dumps({k: v for k, v in world.items() if k != "meta"}, sort_keys=True).encode()
    ).hexdigest()
    return world


def validate(world: dict) -> list:
    """Validate world-model uniqueness, foreign keys, and content hash."""
    errs = []
    try:
        anchor = date.fromisoformat(world["meta"]["anchor_date"])
        emp_list = world["employees"]
        emp = {e["employee_id"]: e for e in emp_list}
        if len(emp) != len(emp_list): errs.append("duplicate employee_id")
        for key in ("email", "username"):
            vals = [e[key] for e in emp_list]
            if len(set(vals)) != len(vals): errs.append(f"duplicate {key}")
        if len({d["code"] for d in world["departments"]}) != len(world["departments"]): errs.append("duplicate department code")
        dept_ids = {d["code"] for d in world["departments"]}
        for key, field in (("systems","system_id"),("customers","customer_id"),("vendors","vendor_id"),("projects","project_id"),("honey","honey_id")):
            vals=[x[field] for x in world.get(key, [])]
            if len(vals)!=len(set(vals)): errs.append(f"duplicate {field}")
        for e in emp_list:
            for fld in ("employee_id", "full_name", "department", "title", "email", "username", "hire_date"):
                if not isinstance(e.get(fld), str) or not e[fld].strip():
                    errs.append(f"{e.get('employee_id')!r}: field {fld} must be a non-empty string")
            if e.get("manager_id") is not None and not isinstance(e["manager_id"], str):
                errs.append(f"{e.get('employee_id')!r}: manager_id must be a string or null")
        if errs:  # wrong types make the relational checks below meaningless
            return errs
        ceos = [e for e in emp_list if e["manager_id"] is None]
        if len(ceos) != 1: errs.append(f"expected 1 top manager, found {len(ceos)}")
        for e in emp_list:
            if e["manager_id"] and e["manager_id"] not in emp: errs.append(f"{e['employee_id']}: unknown manager")
            if e["department"] not in dept_ids: errs.append(f"{e['employee_id']}: unknown department")
            if not e["email"].endswith("@" + world["company"]["domain"]): errs.append(f"{e['employee_id']}: email outside company domain")
            if date.fromisoformat(e["hire_date"]) > anchor: errs.append(f"{e['employee_id']}: hired in the future")
        for d in world["departments"]:
            if d["head_id"] not in emp: errs.append(f"{d['code']}: unknown head")
            if any(m not in emp for m in d["member_ids"]): errs.append(f"{d['code']}: unknown member")
            if any(m not in emp or emp[m]["department"] != d["code"] for m in d["member_ids"]): errs.append(f"{d['code']}: member department mismatch")
        member_count = {}
        for d in world["departments"]:
            if len(d["member_ids"]) != len(set(d["member_ids"])): errs.append(f"{d['code']}: duplicate member_ids")
            if d["head_id"] in emp and emp[d["head_id"]]["department"] != d["code"]: errs.append(f"{d['code']}: head belongs to another department")
            if d["head_id"] not in d["member_ids"]: errs.append(f"{d['code']}: head is not a member")
            for m in d["member_ids"]: member_count[m] = member_count.get(m, 0) + 1
        for eid in emp:
            if member_count.get(eid, 0) != 1: errs.append(f"{eid}: must belong to exactly one department member list (found {member_count.get(eid, 0)})")
        for p in world["projects"]:
            if p["department"] not in dept_ids or p["lead_id"] not in emp or p["lead_id"] not in p["member_ids"] or any(m not in emp for m in p["member_ids"]): errs.append(f"{p['project_id']}: bad members/lead/department")
        for c in world["customers"]:
            if c["account_manager_id"] not in emp: errs.append(f"customer {c['customer_id']}: unknown account manager")
        for v in world["vendors"]:
            if v.get("owner_id") not in emp: errs.append(f"vendor {v['vendor_id']}: unknown owner")
        for x in world["systems"]:
            if x["admin_id"] not in emp: errs.append(f"{x['system_id']}: unknown admin")
            if x["owner_department"] not in dept_ids: errs.append(f"{x['system_id']}: unknown owner department")
        for h in world.get("honey", []):
            if h.get("owner_id") not in emp: errs.append(f"{h['honey_id']}: unknown owner")
        if world["company"]["headcount"] != len(emp_list): errs.append("headcount mismatch")
        sha = hashlib.sha256(json.dumps({k:v for k,v in world.items() if k != "meta"}, sort_keys=True).encode()).hexdigest()
        if world["meta"].get("content_sha256") != sha: errs.append("content_sha256 mismatch")
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        errs.append(f"malformed world model: {e}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--employees", type=int, default=N_EMPLOYEES)
    ap.add_argument("--out", default="world_model.json")
    ap.add_argument("--check", action="store_true", help="build twice, compare, validate")
    a = ap.parse_args()

    w1 = build_world(a.seed, a.employees)
    if a.check:
        w2 = build_world(a.seed, a.employees)
        ok = True
        if json.dumps(w1, sort_keys=True) != json.dumps(w2, sort_keys=True):
            print("FAIL: not deterministic")
            ok = False
        errs = validate(w1)
        for e in errs:
            print("FAIL:", e)
        ok = ok and not errs
        print("OK" if ok else "CHECK FAILED", "| sha256", w1["meta"]["content_sha256"][:16])
        sys.exit(0 if ok else 1)

    errs = validate(w1)
    if errs:
        print("\n".join(errs))
        sys.exit(1)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(w1, f, indent=2, ensure_ascii=False)
    print(f"wrote {a.out}: {len(w1['employees'])} employees, {len(w1['departments'])} depts, "
          f"{len(w1['customers'])} customers, {len(w1['vendors'])} vendors, {len(w1['projects'])} projects")


if __name__ == "__main__":
    main()
