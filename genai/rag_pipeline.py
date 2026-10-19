"""
rag_pipeline.py  (A4, Day 4-5)  Retrieval (pgvector) + prompt template + Ollama calls.

Pieces
  OllamaClient      generate() and embed() over the local Ollama HTTP API (stdlib only)
  InMemoryStore     cosine search in Python (tests, or no database available)
  PgVectorStore     real pgvector table kb_chunks (schema.sql), cosine distance <=>
  RAG               ingest(world) + retrieve(query) + build_prompt() + generate()

Embedding prefixes: nomic-embed-text expects "search_document: " on stored text
and "search_query: " on queries.
"""
import hashlib
import json
import math
import re
import urllib.request

from knowledge_base import build_chunks

EMB_DIM = 768
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


# ---------------------------------------------------------------- Ollama
class OllamaClient:
    def __init__(self, host="http://localhost:11434", gen_model="llama3.1:8b",
                 emb_model="nomic-embed-text", timeout=300):
        self.host, self.gen_model, self.emb_model, self.timeout = host, gen_model, emb_model, timeout

    def _post(self, path, payload):
        req = urllib.request.Request(self.host + path, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def generate(self, prompt, seed=42, temperature=0.7, max_tokens=400):
        out = self._post("/api/generate", {
            "model": self.gen_model, "prompt": prompt, "stream": False,
            "options": {"temperature": temperature, "seed": seed, "num_predict": max_tokens}})
        return out.get("response", "")

    def embed(self, texts):
        texts = list(texts)
        out = self._post("/api/embed", {"model": self.emb_model, "input": texts})
        vectors = out.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("Ollama embedding count does not match input count")
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != EMB_DIM or any(not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) for x in vector):
                raise ValueError(f"Ollama embedding must contain {EMB_DIM} finite numeric dimensions")
        return vectors


# ---------------------------------------------------------------- stores
def _cos(a, b):
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _validate_embedding_batch(chunks, embeddings):
    if len(chunks) != len(embeddings): raise ValueError("embedding count does not match chunks")
    if any(not isinstance(v, (list, tuple)) or len(v) != EMB_DIM or any(not isinstance(x, (int,float)) or isinstance(x,bool) or not math.isfinite(x) for x in v) for v in embeddings):
        raise ValueError(f"embeddings must be finite numeric vectors of dimension {EMB_DIM}")


class InMemoryStore:
    def __init__(self):
        self.rows = {}

    def init_schema(self):
        pass

    def upsert(self, chunks, embeddings, world_sha=""):
        _validate_embedding_batch(chunks, embeddings)
        if world_sha:
            self.rows = {cid: pair for cid, pair in self.rows.items() if pair[0].get("world_sha") == world_sha}
        for c, e in zip(chunks, embeddings):
            c = dict(c, world_sha=world_sha)
            self.rows[c["chunk_id"]] = (c, list(e))

    def count(self):
        return len(self.rows)

    def search(self, vec, k=6, kinds=None):
        scored = [(_cos(vec, e), c) for c, e in self.rows.values() if not kinds or c["kind"] in kinds]
        scored.sort(key=lambda t: -t[0])
        return [dict(c, score=round(s, 4)) for s, c in scored[:k]]


class PgVectorStore:
    """Needs `pip install "psycopg[binary]"` and the table from schema.sql."""

    def __init__(self, dsn="postgresql://labyrinth:labyrinth@localhost:5432/labyrinth"):
        import psycopg  # imported here so the rest works without it
        self._psycopg = psycopg
        self.dsn = dsn

    @staticmethod
    def _vec(v):
        return "[" + ",".join(f"{x:.7f}" for x in v) + "]"

    def init_schema(self, schema_path="schema.sql"):
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
        with self._psycopg.connect(self.dsn, autocommit=True) as con:
            con.execute(sql)

    def upsert(self, chunks, embeddings, world_sha=""):
        _validate_embedding_batch(chunks, embeddings)
        with self._psycopg.connect(self.dsn) as con, con.cursor() as cur:
            if world_sha:
                cur.execute("DELETE FROM kb_chunks WHERE world_sha <> %s", (world_sha,))
            for c, e in zip(chunks, embeddings):
                cur.execute(
                    """INSERT INTO kb_chunks (chunk_id, kind, text, meta, embedding, world_sha)
                       VALUES (%s, %s, %s, %s::jsonb, %s::vector, %s)
                       ON CONFLICT (chunk_id) DO UPDATE SET kind=EXCLUDED.kind, text=EXCLUDED.text,
                           meta=EXCLUDED.meta, embedding=EXCLUDED.embedding, world_sha=EXCLUDED.world_sha""",
                    (c["chunk_id"], c["kind"], c["text"], json.dumps(c["meta"]), self._vec(e), world_sha))

    def count(self):
        with self._psycopg.connect(self.dsn) as con:
            return con.execute("SELECT count(*) FROM kb_chunks").fetchone()[0]

    def search(self, vec, k=6, kinds=None):
        q = ("SELECT chunk_id, kind, text, meta, 1 - (embedding <=> %s::vector) AS score FROM kb_chunks "
             + ("WHERE kind = ANY(%s) " if kinds else "")
             + "ORDER BY embedding <=> %s::vector LIMIT %s")
        v = self._vec(vec)
        args = [v] + ([list(kinds)] if kinds else []) + [v, k]
        with self._psycopg.connect(self.dsn) as con:
            rows = con.execute(q, args).fetchall()
        return [{"chunk_id": r[0], "kind": r[1], "text": r[2], "meta": r[3], "score": round(float(r[4]), 4)}
                for r in rows]


# ---------------------------------------------------------------- prompt template
EMAIL_TEMPLATE = """You write internal emails for the fictional company {company} ({industry}, {city}).
Tone: {tone}.

CONTEXT (the only facts you may use):
{context}

SENDER:    {s_name} <{s_email}>, {s_title}
RECIPIENT: {r_name} <{r_email}>, {r_title}
TOPIC:     {topic}

Rules:
- Write a realistic internal email body of 80-130 words.
- Address the recipient by first name and sign off with "Best regards," then the sender's full name.
- Use ONLY people, systems, projects and customers named in the CONTEXT. Do not invent names, emails, or companies.
- No placeholders like [Name] or {{date}}. No mention of being an AI.
- Output format: first line "Subject: <subject>", a blank line, then the body. Nothing else."""

MEMO_TEMPLATE = """You write internal memos for the fictional company {company} ({industry}, {city}).
Tone: {tone}.

CONTEXT (the only facts you may use):
{context}

FROM:     {s_name}, {s_title}
AUDIENCE: {audience}
TOPIC:    {topic}

Rules:
- Write a memo body of 110-170 words, in short paragraphs, announcing or reminding staff about the topic.
- Use ONLY people, systems, projects and customers named in the CONTEXT. Do not invent names, emails, or companies.
- End with "{s_name}".
- No placeholders like [Name] or {{date}}. No mention of being an AI.
- Output format: first line "Subject: <subject>", a blank line, then the body. Nothing else."""


class RAG:
    def __init__(self, store, llm):
        self.store, self.llm = store, llm

    # --- ingestion
    def ingest(self, world, batch=32):
        chunks = build_chunks(world)
        self.store.init_schema()
        for i in range(0, len(chunks), batch):
            part = chunks[i:i + batch]
            embs = self.llm.embed([DOC_PREFIX + c["text"] for c in part])
            _validate_embedding_batch(part, embs)
            self.store.upsert(part, embs, world["meta"]["content_sha256"])
        return len(chunks)

    # --- retrieval
    def retrieve(self, query, k=6, kinds=None):
        vectors = self.llm.embed([QUERY_PREFIX + query])
        _validate_embedding_batch([None], vectors)
        return self.store.search(vectors[0], k=k, kinds=kinds)

    @staticmethod
    def format_context(chunks):
        return "\n".join(f"- {c['text']}" for c in chunks)

    # --- prompts
    def email_prompt(self, world, sender, recipient, topic, k=6):
        hits = self.retrieve(f"{topic} {sender['department']} {recipient['department']}", k=k,
                             kinds=["project", "system", "customer", "vendor", "department"])
        c = world["company"]
        return EMAIL_TEMPLATE.format(
            company=c["name"], industry=c["industry"], city=c["hq_city"], tone=c["tone"],
            context=self.format_context(hits),
            s_name=sender["full_name"], s_email=sender["email"], s_title=sender["title"],
            r_name=recipient["full_name"], r_email=recipient["email"], r_title=recipient["title"],
            topic=topic), hits

    def memo_prompt(self, world, sender, audience, topic, k=6):
        hits = self.retrieve(f"{topic} {sender['department']}", k=k,
                             kinds=["project", "system", "department"])
        c = world["company"]
        return MEMO_TEMPLATE.format(
            company=c["name"], industry=c["industry"], city=c["hq_city"], tone=c["tone"],
            context=self.format_context(hits), s_name=sender["full_name"], s_title=sender["title"],
            audience=audience, topic=topic), hits


# ---------------------------------------------------------------- offline stand-ins (tests / dry runs)
class FakeLLM:
    """Deterministic stand-in so the pipeline can be tested without Ollama."""

    def embed(self, texts):
        """Bag-of-words vectors (lexical overlap => closer), so retrieval behaves sensibly in tests."""
        out = []
        for t in texts:
            v = [0.0] * EMB_DIM
            for w in set(re.findall(r"[a-z0-9]+", t.lower())) - {"search_document", "search_query"}:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % EMB_DIM] += 1.0
            out.append(v)
        return out

    SENTENCES = [
        "Could you review the latest figures and let me know if anything looks off before the end of the week?",
        "I have attached nothing yet, but the numbers from last month are ready if you want to compare them.",
        "The team raised a few questions during Sunday's meeting and I would like to close them quickly.",
        "Please confirm whether the current plan still works for your side, or tell me what needs to change.",
        "We are slightly behind where we expected to be, although nothing here is urgent at the moment.",
        "If it helps, I can walk you through the details in ten minutes tomorrow morning.",
        "A few of the older items are still open and I would rather clear them before the next review.",
        "Thanks for the quick turnaround last time, it made the whole process much easier for everyone.",
        "Let me know who else should be copied so that nobody is surprised later on.",
        "I will check again on Thursday and escalate to the department head only if we are still stuck.",
        "Our records show the last update was a few weeks ago, so a short refresh would be useful.",
        "The deadline is not moving, so any early feedback from you would be very welcome.",
    ]

    def generate(self, prompt, seed=42, temperature=0.7, max_tokens=400):
        import random
        import re
        rng = random.Random(seed)
        topic = re.sub(r"\s*\(the (?:email|memo) .*\)\s*$", "", re.search(r"TOPIC:\s+(.+)", prompt).group(1).strip())
        picks = " ".join(rng.sample(self.SENTENCES, 5))
        if prompt.startswith("You write internal memos"):
            frm = re.search(r"FROM:\s+(.+?),", prompt).group(1)
            return f"Subject: {topic}\n\nDear colleagues,\n\nThis memo concerns {topic.lower()}. {picks}\n\nThank you for your cooperation.\n\n{frm}"
        r = re.search(r"RECIPIENT:\s+(\S+)", prompt).group(1)
        s = re.search(r"SENDER:\s+(.+?) <", prompt).group(1)
        return f"Subject: {topic}\n\nHi {r},\n\nFollowing up on {topic.lower()}. {picks}\n\nBest regards,\n{s}"
