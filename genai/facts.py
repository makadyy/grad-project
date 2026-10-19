"""
facts.py  (A4, Day 4)  company.json -> list of fact "chunks" for retrieval.

One chunk = one short, self-contained fact paragraph (what the LLM will read as CONTEXT).
Chunk ids are stable (emp:E1004, proj:P03 ...) so re-ingesting is an upsert, not a duplicate.
"""
import json


def load_world(path="company.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_chunks(world: dict) -> list:
    emp = {e["employee_id"]: e for e in world["employees"]}
    dep = {d["code"]: d for d in world["departments"]}
    c = world["company"]
    chunks = []

    def add(cid, kind, text, **meta):
        chunks.append({"chunk_id": cid, "kind": kind, "text": text, "meta": meta})

    add("company:main", "company",
        f"{c['name']} is a {c['industry']} company founded in {c['founded']}, headquartered in {c['hq_city']}. "
        f"{c['mission']} Staff email addresses end in @{c['domain']}. Writing tone: {c['tone']}.")

    for d in world["departments"]:
        head = emp[d["head_id"]]
        add(f"dept:{d['code']}", "department",
            f"The {d['name']} department ({d['code']}) is led by {head['full_name']}, {head['title']}, "
            f"and has {len(d['member_ids'])} members.", department=d["code"])

    for e in world["employees"]:
        mgr = emp.get(e["manager_id"]) if e["manager_id"] else None
        add(f"emp:{e['employee_id']}", "employee",
            f"{e['full_name']} is {e['title']} in {dep[e['department']]['name']} ({e['department']}), "
            f"based at {e['office']}, email {e['email']}"
            + (f", reports to {mgr['full_name']} ({mgr['title']})." if mgr else ", and is the top executive."),
            department=e["department"], employee_id=e["employee_id"])

    for p in world["projects"]:
        lead = emp[p["lead_id"]]
        members = ", ".join(emp[m]["full_name"] for m in p["member_ids"])
        add(f"proj:{p['project_id']}", "project",
            f"Project '{p['name']}' ({p['department']} department) is {p['status'].replace('_', ' ')}, "
            f"started {p['start']}, led by {lead['full_name']}. Team: {members}.",
            department=p["department"], project_id=p["project_id"])

    for s in world["systems"]:
        adm = emp[s["admin_id"]]
        add(f"sys:{s['system_id']}", "system",
            f"{s['name']} runs on {s['host']} ({s['kind']}), owned by the {s['owner_department']} department, "
            f"administered by {adm['full_name']}.", department=s["owner_department"], system_id=s["system_id"])

    for cu in world["customers"]:
        am = emp[cu["account_manager_id"]]
        add(f"cust:{cu['customer_id']}", "customer",
            f"Customer {cu['company']} (id {cu['customer_id']}, {cu['city']}) has contact {cu['contact_name']}; "
            f"credit limit {cu['credit_limit']} EGP; account manager {am['full_name']}.",
            department="SAL", customer_id=cu["customer_id"])

    for v in world["vendors"]:
        ow = emp[v["owner_id"]]
        add(f"vend:{v['vendor_id']}", "vendor",
            f"Vendor {v['name']} (id {v['vendor_id']}) supplies {v['category']}; relationship owner {ow['full_name']}.",
            department="PRC", vendor_id=v["vendor_id"])
    return chunks
