# The AI Parts of LabyrinthAI — Explained Simply

## The story of one attacker

Imagine a **thief trying to break into a bank**. Instead of locking the door, the bank lets him
into a **fake bank** that looks real, while hidden cameras watch everything he does. The 4 AI
parts are 4 jobs inside that fake bank.

---

## 1. Gatekeeper (Abdelrahman) — the guard at the door

- **Question it answers:** "Is this visitor a thief or a normal customer?"
- **How:** It looks at internet traffic: how many messages are sent, how fast, how big. The
  dataset (CIC-IDS2018) contains millions of recorded connections, each marked "normal" or
  "attack."
- We train a model (XGBoost) on that data so it learns patterns like "normal users don't send
  1000 login attempts a minute."
- **If it says "thief"**, the system quietly sends him into the fake bank instead of the real one.

---

## 2. Profiler (Seif) — the person watching the cameras

Now the thief is inside the fake bank. The Profiler asks: **"Is he an amateur or a professional?"**

It decides by watching what he does:

| What he does | What it suggests |
|---|---|
| Types slowly, makes typos | Amateur |
| Types fast, knows exactly which commands to run | Pro |
| Tries to get admin rights | Dangerous |
| Opens files like `passwords.txt` | Hunting for valuables |

**The job, in 4 steps:**

1. **Make a list of ~30 things worth counting.** Number of commands typed, average time between
   commands, number of typos, did he try to become admin… That list is `session_features.md`.
2. **Write the grading rules (the rubric).** Example: "if he tried admin and types fast → Pro."
   Like a teacher's marking scheme.
3. **Write code that updates those counts live.** Every time the thief types something, the
   numbers update immediately. That's the "incremental feature extractor."
4. **Explain the decision (SHAP).** When the system says "Pro," it also says *why*: "because he
   tried admin 3 times and typed very fast." The security analyst sees this on the dashboard.

---

## 3. Maze (Malak) — the manager deciding what to do with him

Based on how skilled the thief is, the Maze picks one of 5 moves:

| Move | Meaning |
|---|---|
| **OBSERVE** | Just keep watching |
| **DEEPEN** | Open a new fake room so he goes further in |
| **LURE** | Leave fake bait (a fake password on a desk) |
| **SLOW** | Make things slow, to waste his time |
| **CONTAIN** | He's too dangerous — kick him out and lock doors |

- **Version 1:** simple fixed rules, e.g. "if Pro and getting close to something important →
  CONTAIN."
- **Version 2 (RL / Reinforcement Learning):** the computer plays this game thousands of times
  against simulated thieves and learns the best moves by itself. "Gymnasium MazeEnv" = the
  practice game for the AI.
- **Shield:** safety rules the AI can never break, e.g. "if he's about to reach the real system,
  always CONTAIN."

---

## 4. GenAI (Martina) — the set designer

A fake bank needs fake but **believable** stuff inside: emails, memos, employee records. If one
email mentions an employee who doesn't exist, the thief realizes it's a trap.

1. **Invent a fake company first:** names, departments, who's the manager of whom
   (`world_model.json`).
2. **Use an AI writer (Llama, running locally) to write emails and memos** about that company.
3. **Before writing, give the AI the facts ("RAG").** Before writing an email from "Ahmed in
   Finance," the system looks up who Ahmed is and gives that to the AI, so it never invents a
   contradiction.
4. **Check everything (quality gate):** every name and file mentioned must exist, and no real
   person's data may appear.

---

## Summary in one line each

- **Gatekeeper (Abdelrahman):** is it an attacker? → send him into the fake world
- **Profiler (Seif):** how skilled is he, and why do we think that
- **Maze (Malak):** what do we do with him next
- **GenAI (Martina):** make the fake world look real

```
attacker → [Gatekeeper] → fake world → [Profiler] → [Maze] → next move
                                ↑
                          [GenAI fills it with fake content]
```

---

## File map

```
README.md              this file
requirements.txt       every Python package the project needs (one install)
pytest.ini             tells pytest where the tests are
```

### `gatekeeper/` — Gatekeeper (Abdelrahman)
| File | Role |
|---|---|
| `01_prepare_parquet.py` | Step 1: clean the raw CIC-IDS2018 CSVs (drop IDs, bad rows, duplicates) → `out/parquet/` |
| `02_eda_split.py` | Step 2: count classes per day, split into train / val / test + one unseen day |
| `03_baselines.py` | Step 3: train Decision Tree + XGBoost, write the scores |
| `build_dataset.py` | Older all-in-one pipeline (streams `raw/` → `out/`). Kept for reference |
| `requirements.txt` | Packages for this part only |
| `raw/`, `liu2022/`, `out/` | The dataset and outputs. Big, **not** in git |

### `profiler/` — Profiler (Seif)
| File | Role |
|---|---|
| `src/profiler_xai/feature_extractor.py` | Turns live events into the 30 session numbers (updates as events arrive) |
| `src/profiler_xai/schemas.py` | The shape of an event and of a feature record |
| `src/profiler_xai/shap_service.py` | Explains a prediction ("Pro because…") with SHAP |
| `docs/session_features.md` | The list of the 30 features and where each comes from |
| `docs/evaluation_rubric.md` | Grading rules: amateur vs. pro |
| `examples/events.jsonl` | Sample events to try the extractor on |
| `tests/` | Tests |

### `maze/` — Maze (Malak)
| File | Role |
|---|---|
| `maze_env.py` | The practice game (Gymnasium env): state, 5 moves, rewards, shield |
| `policy.py` | Version 1 fixed rules that pick the move |
| `maze_spec.md` | The rules of the game written out |
| `tests/` | Tests |

### `genai/` — GenAI (Martina)
| File | Role |
|---|---|
| `world_model.py` → `world_model.json` | Builds the fake company (people, departments, systems, bait files) |
| `knowledge_base.py` | Cuts the company into small facts the AI can look up |
| `rag_pipeline.py` | Talks to Llama (Ollama) and looks up facts before writing (RAG) |
| `generators.py` | Writes emails, memos and fake database rows |
| `quality_gate.py` | Rejects anything that mentions people/files that don't exist |
| `build_artifacts.py` | Runs it all: plan → write → check → retry → save to `out/` |
| `gen_test.py` | First check that Ollama + Llama work on this machine |
| `schema.sql`, `docker-compose.yml` | The Postgres + pgvector database for the facts |
| `test_pipeline.py` | Tests |

### `integration/`
| File | Role |
|---|---|
| `run_smoke.py` | Runs Profiler → Maze with GenAI's fake company, end to end, offline |
| `test_integration.py` | Same thing as a test |

### Run it
```bash
pip install -r requirements.txt
pytest -q                                   # all tests
python integration/run_smoke.py             # all parts together
cd gatekeeper && python 01_prepare_parquet.py && python 02_eda_split.py && python 03_baselines.py
```

---

## Data fields

### Gatekeeper — one row = one network connection (CIC-IDS2018, Liu 2022 fixed version)
- **69 number columns.** Removed first: Flow ID, IPs, ports, timestamp (they would let the
  model cheat by memorising addresses).
  - **Size & count:** `Tot Fwd Pkts`, `Tot Bwd Pkts`, `TotLen Fwd Pkts`, `TotLen Bwd Pkts`, packet length max/min/mean/std (fwd, bwd, overall), `Pkt Size Avg`, segment sizes, header lengths, subflow counts
  - **Speed & timing:** `Flow Duration`, `Flow Byts/s`, `Flow Pkts/s`, `Fwd Pkts/s`, `Bwd Pkts/s`, IAT (time between packets) mean/std/max/min, Active/Idle mean/std/max/min
  - **TCP flags:** `FIN`, `SYN`, `RST`, `PSH`, `ACK`, `URG`, `CWE`, `ECE` counts, `Fwd PSH/URG Flags`
  - **Other:** `Protocol`, `Down/Up Ratio`, `Init Fwd/Bwd Win Byts`, `Fwd Act Data Pkts`
  - Full list: `gatekeeper/out/feature_columns.json`
- **`Label`** (the answer, 15 classes): `Benign`, `Bot`, `Infilteration`, `SQL Injection`,
  `Brute Force -Web`, `Brute Force -XSS`, `FTP-BruteForce`, `SSH-Bruteforce`, 4 × `DoS`
  (GoldenEye, Hulk, SlowHTTPTest, Slowloris), 3 × `DDoS` (HOIC, LOIC-UDP, LOIC-HTTP)
- **`Day`**: which capture day the row came from (one whole day is kept unseen for testing)

### Profiler — one row = one attacker session inside the fake world
- **Input event** (from Cowrie / portal / database / Wazuh): `session_id`, `event_id`,
  `timestamp`, `source`, `event_type`, plus optional `src_ip`, `username`, `command`,
  `bytes_in`, `bytes_out`, `status`, `severity`, `resource`
- **30 output features:**
  - **Volume & pace:** `event_count`, `duration_seconds`, `events_per_minute`, `inter_event_seconds_mean`, `inter_event_seconds_max`
  - **Per source:** `cowrie_event_count`, `portal_event_count`, `database_event_count`, `wazuh_alert_count`
  - **Logins:** `login_attempt_count`, `login_failure_count`, `login_success_count`, `login_failure_rate`, `portal_auth_failure_count`
  - **Commands & files:** `command_event_count`, `unique_command_count`, `suspicious_command_count`, `file_download_event_count`, `file_upload_event_count`, `network_connection_count`
  - **Data moved:** `bytes_in_total`, `bytes_out_total`, `bytes_total`, `distinct_resource_count`
  - **Actions:** `portal_admin_action_count`, `database_read_count`, `database_write_count`, `database_delete_count`
  - **Alerts:** `wazuh_high_severity_count`, `wazuh_critical_severity_count`
  - Definitions: `profiler/docs/session_features.md`

### Maze — the game state (each 0–3, except `turn`)
`turn` (max 12), `intel` (how much we learned), `exposure` (how much he has seen),
`alert` (how suspicious he is), `progress` (how close to something real), `contained`.
Moves: `OBSERVE`, `DEEPEN`, `LURE`, `SLOW`, `CONTAIN`.

### GenAI — the fake company (`genai/world_model.json`)
| Table | Fields |
|---|---|
| `employees` | `employee_id`, `full_name`, `email`, `department`, `title`, `manager_id`, `hire_date`, `salary_band`, `phone`, `username`, `office` |
| `departments` | `code`, `name`, `head_id`, `member_ids` |
| `systems` | `system_id`, `name`, `kind`, `owner_department`, `host`, `sensitivity`, `admin_id` |
| `customers` | `customer_id`, `company`, `contact_name`, `email`, `city`, `credit_limit`, `account_manager_id` |
| `vendors` | `vendor_id`, `name`, `category`, `contact_email`, `iban_last4`, `owner_id` |
| `projects` | `project_id`, `name`, `department`, `lead_id`, `member_ids`, `start`, `status` |
| `honey` (bait) | `honey_id`, `kind`, `path`, `owner_id`, `lure` |
