"""
quality_gate.py  (A4, Day 6)  Quality gate v1.

An artifact is ACCEPTED only if every hard check passes. Each failure comes back as a short
reason code, so build_artifacts.py can count why things get rejected and you can tune prompts.

Text artifacts (email, memo)
  structure     Subject line, body length, greeting / sign-off present, not cut off mid-sentence
  placeholders  [Name], {{x}}, <tag>, lorem ipsum, "as an AI", "the context provided" ...
  identities    every e-mail address exists in the world; sign-off is the real sender; no invented
                person names (heuristic, see NAME_LIKE_FIRST); no other employee named unless allowed
  dates         no date after the world's anchor date
  sensitive     no passwords / card-like numbers in the text
  duplicates    near-duplicate of an already accepted artifact (word-shingle Jaccard)

DB batches
  columns / types, primary-key uniqueness, foreign keys (customer, order, employee), dates, amounts

This is v1: rule-based and deliberately strict. It cannot judge style or factual realism.
"""
import re
import math
from dataclasses import dataclass, field
from datetime import date

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,40}\]|\{\{?[^}\n]{1,40}\}?\}|<[A-Za-z][^>\n]{0,40}>|lorem ipsum|\bTBD\b|\bXXX+\b", re.I)
META_PHRASES = ["as an ai", "language model", "the context provided", "according to the context", "in the context",
                "world model", "i cannot", "i can't", "here is the email", "here's the email", "here is a memo",
                "here's a memo", "certainly!", "sure!"]
ISO_DATE_RE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
YEAR_RE = re.compile(r"\b(20[3-9]\d|2[1-9]\d\d)\b")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SECRET_RE = re.compile(r"\b(password|passwd|pwd|api[_ -]?key|secret)\s*[:=]\s*\S+", re.I)
NAME_BIGRAM_RE = re.compile(r"\b([A-Z][a-z]{2,}) ([A-Z][a-z]{2,})\b")

# first names that would signal an invented person (extended at runtime with every name in the world)
NAME_LIKE_FIRST = set("""James John Robert Michael William David Richard Joseph Thomas Charles Mary Patricia Jennifer
Linda Elizabeth Barbara Susan Jessica Sarah Karen Nancy Lisa Daniel Matthew Anthony Mark Paul Steven Andrew Kevin Brian
George Emily Michelle Laura Amanda Ahmed Mohamed Mohammed Ali Omar Hassan Mahmoud Youssef Karim Sara Nour Mona Fatma
Sam Peter Henry Alex Chris Jane Anna Emma Olivia""".split())

SIGNOFF_RE = re.compile(r"best regards,?\s*\n+\s*(.+)", re.I)


@dataclass
class GateResult:
    ok: bool
    reasons: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def parse_text(raw: str):
    """'Subject: x\\n\\nbody'  ->  (subject, body) or (None, raw)."""
    lines = raw.strip().splitlines()
    if not lines or not lines[0].lower().startswith("subject:"):
        return None, raw.strip()
    subject = lines[0].split(":", 1)[1].strip()
    return subject, "\n".join(lines[1:]).strip()


def _shingles(text, n=4):
    w = re.findall(r"[a-z']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def _luhn(num: str) -> bool:
    d = [int(c) for c in num][::-1]
    s = sum(d[0::2]) + sum(sum(divmod(x * 2, 10)) for x in d[1::2])
    return s % 10 == 0


class QualityGate:
    def __init__(self, world, dup_threshold=0.6):
        self.world = world
        self.anchor = date.fromisoformat(world["meta"]["anchor_date"])
        self.dup_threshold = dup_threshold
        self.emp_by_email = {e["email"].lower(): e for e in world["employees"]}
        self.known_emails = set(self.emp_by_email) | {c["email"].lower() for c in world["customers"]} \
            | {v["contact_email"].lower() for v in world["vendors"]}
        self.emp_names = {e["full_name"] for e in world["employees"]}
        self.known_people = set(self.emp_names) | {c["contact_name"] for c in world["customers"]}
        self.first_names = NAME_LIKE_FIRST | {e["first_name"] for e in world["employees"]} \
            | {c["contact_name"].split()[0] for c in world["customers"]}
        # capitalised phrases that are legitimate even if they look like names
        self.known_phrases = set()
        for d in world["departments"]:
            self.known_phrases.add(d["name"])
        for p in world["projects"]:
            self.known_phrases.add(p["name"])
        for s in world["systems"]:
            self.known_phrases.add(s["name"])
        for e in world["employees"]:
            self.known_phrases.add(e["title"])
        self.known_phrases |= {world["company"]["name"]}
        self._accepted = {"email": [], "memo": []}
        self._seen_pk = set()

    # ------------------------------------------------------------- text
    def check_text(self, kind, raw, sender, recipient=None, allowed_names=(), register=True):
        reasons, warnings = [], []
        subject, body = parse_text(raw)
        if subject is None:
            reasons.append("no_subject_line")
        elif not 3 <= len(subject.split()) <= 14:
            reasons.append("subject_length")
        words = len(body.split())
        lo, hi = (60, 190) if kind == "email" else (80, 240)
        if words < lo:
            reasons.append("too_short")
        if words > hi:
            reasons.append("too_long")
        if sum(ord(c) > 127 for c in raw) > 0.03 * max(1, len(raw)):
            reasons.append("non_english")

        low = raw.lower()
        if PLACEHOLDER_RE.search(raw):
            reasons.append("placeholder")
        if any(p in low for p in META_PHRASES):
            reasons.append("meta_phrase")

        # structure: greeting + sign-off
        if kind == "email":
            if recipient and recipient["first_name"] not in body.split("\n")[0]:
                reasons.append("no_greeting_to_recipient")
            m = SIGNOFF_RE.search(body)
            if not m:
                reasons.append("no_signoff")
            elif m.group(1).strip().rstrip(".") != sender["full_name"]:
                reasons.append("wrong_signoff_name")
        else:
            last = body.strip().splitlines()[-1].strip().rstrip(".") if body.strip() else ""
            if last != sender["full_name"]:
                reasons.append("memo_missing_sender_signoff")
        if body and body.strip()[-1] not in ".!?" and not body.strip().splitlines()[-1].strip().rstrip(".") == sender["full_name"]:
            reasons.append("truncated")

        # identities
        for addr in EMAIL_RE.findall(raw):
            if addr.lower() not in self.known_emails:
                reasons.append("unknown_email")
                break
        allowed = set(allowed_names) | {sender["full_name"]} | ({recipient["full_name"]} if recipient else set())
        for name in self.emp_names - allowed:
            if name in raw:
                reasons.append("mentions_unlisted_employee")
                break
        for m in NAME_BIGRAM_RE.finditer(raw):
            full = f"{m.group(1)} {m.group(2)}"
            if m.group(1) in self.first_names and full not in self.known_people \
                    and not any(full in ph for ph in self.known_phrases):
                reasons.append("invented_person_name")
                warnings.append(f"name: {full}")
                break

        # dates
        for y, mo, d in ISO_DATE_RE.findall(raw):
            try:
                if date(int(y), int(mo), int(d)) > self.anchor:
                    reasons.append("future_date")
                    break
            except ValueError:
                reasons.append("bad_date")
                break
        if YEAR_RE.search(raw):
            reasons.append("far_future_year")

        # sensitive
        if SECRET_RE.search(raw):
            reasons.append("secret_in_text")
        for m in CARD_RE.finditer(raw):
            digits = re.sub(r"\D", "", m.group())
            if 13 <= len(digits) <= 19 and _luhn(digits):
                reasons.append("card_like_number")
                break

        # duplicates
        sh = _shingles(body)
        for prev in self._accepted.get(kind, []):
            inter = len(sh & prev)
            if inter / max(1, len(sh | prev)) >= self.dup_threshold:
                reasons.append("near_duplicate")
                break

        reasons = list(dict.fromkeys(reasons))
        ok = not reasons
        if ok and register:
            self._accepted.setdefault(kind, []).append(sh)
        return GateResult(ok, reasons, warnings)

    # ------------------------------------------------------------- DB
    def check_db_batch(self, table, rows, db_tables, ref=None, register=True):
        """ref = dict of lookup sets, e.g. {'customer_ids': {...}, 'order_ids': {...}, 'employee_ids': {...}}"""
        ref = ref or {}
        reasons = []
        cols = db_tables[table]
        pk = list(cols)[0]
        if not rows:
            return GateResult(False, ["empty_batch"])
        py = {"int": int, "text": str, "numeric": (int, float), "date": str, "bool": bool}
        for r in rows:
            if set(r) != set(cols):
                reasons.append("wrong_columns")
                break
            bad = [c for c, t in cols.items()
                   if r[c] is not None and (not isinstance(r[c], py[t])
                                            or (t in ("int", "numeric") and isinstance(r[c], bool))
                                            or (t == "numeric" and isinstance(r[c], float)
                                                and not math.isfinite(r[c])))]
            if bad:
                reasons.append("wrong_type")
                break
        else:
            pks = [r[pk] for r in rows]
            if len(set(pks)) != len(pks) or any((table, p) in self._seen_pk for p in pks):
                reasons.append("duplicate_primary_key")
            for r in rows:
                for c, t in cols.items():
                    if t == "date" and r[c]:
                        try:
                            if date.fromisoformat(r[c]) > self.anchor:
                                reasons.append("future_date")
                        except ValueError:
                            reasons.append("bad_date")
                if table in ("orders", "invoices", "customers") and any(
                        isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0 for v in r.values()):
                    reasons.append("negative_value")
                if table == "orders" and "customer_ids" in ref and r["customer_id"] not in ref["customer_ids"]:
                    reasons.append("fk_customer")
                if table == "invoices" and "order_ids" in ref and r["order_id"] not in ref["order_ids"]:
                    reasons.append("fk_order")
                if table == "invoices" and r["due"] and r["issued"] and r["due"] < r["issued"]:
                    reasons.append("due_before_issued")
                if table == "customers" and "employee_ids" in ref and r["account_manager_id"] not in ref["employee_ids"]:
                    reasons.append("fk_employee")
                if table == "vendors" and "owner_id" in r and "employee_ids" in ref and r["owner_id"] not in ref["employee_ids"]:
                    reasons.append("fk_employee")
                if table == "employees" and not str(r["email"]).lower() in self.known_emails:
                    reasons.append("unknown_email")
        reasons = list(dict.fromkeys(reasons))
        ok = not reasons
        if ok and register:
            self._seen_pk |= {(table, r[pk]) for r in rows}
        return GateResult(ok, reasons)
