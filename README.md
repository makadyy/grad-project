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

## Where everything lives

One folder per job. Same names as the 4 parts above.

| Folder | Part | What's inside, simply |
|---|---|---|
| `gatekeeper/` | 1. Gatekeeper | 3 scripts you run in order: **clean** the data → **split** it → **train** the model |
| `profiler/` | 2. Profiler | The code that **counts** what the thief does, and the code that **explains** the verdict |
| `maze/` | 3. Maze | The **game** (moves + rewards) and the **rules** that pick the next move |
| `genai/` | 4. GenAI | Builds the **fake company**, **writes** fake emails/memos, and **checks** them |
| `integration/` | all 4 | One test that runs the parts **together** to prove they connect |

The most important files:

- `gatekeeper/01_prepare_parquet.py` → `02_eda_split.py` → `03_baselines.py` — run in this order
- `profiler/src/profiler_xai/feature_extractor.py` — turns the thief's actions into numbers
- `maze/maze_env.py` — the game; `maze/policy.py` — the rules
- `genai/world_model.json` — the fake company; `genai/build_artifacts.py` — makes all the fake files
- `requirements.txt` — install everything with `pip install -r requirements.txt`
- Run all tests with `pytest -q`

---

## What the data looks like

### Gatekeeper — "one row = one connection"

Every time a computer talks to another, that's one row. For each row we know:

- **How much** was sent (number of packets, total bytes)
- **How fast** (packets per second, gap between packets, how long it lasted)
- **What kind** of messages (TCP "flags" — e.g. lots of SYN = someone knocking on many doors)
- **The answer:** `Benign` (normal) or which attack it was — e.g. DoS, DDoS, brute-force
  password guessing, SQL injection, Bot

69 number columns in total. We **delete** IP addresses and times first, so the model learns
*behaviour*, not "this IP was bad."

### Profiler — "one row = one thief's visit"

Every action the thief does (log in, type a command, open a file) is an **event**. We turn all
his events into **30 numbers**, for example:

| Number | Plain meaning |
|---|---|
| `events_per_minute` | How fast he works |
| `login_failure_count` | How many wrong passwords |
| `unique_command_count` | How many different commands he knows |
| `suspicious_command_count` | Commands like downloading tools |
| `database_delete_count` | Did he try to delete data |
| `bytes_out_total` | How much data he tried to take out |

Full list with definitions: `profiler/docs/session_features.md`.

### Maze — "what the manager sees"

Five meters, each from 0 (low) to 3 (high): **intel** (how much we learned about him),
**exposure** (how much he has seen), **alert** (how suspicious he is), **progress** (how close he
is to something real), **contained** (is he locked in). The game ends after 12 turns.

### GenAI — "the fake company"

A made-up company with **employees** (name, email, job, manager), **departments**, **computer
systems**, **customers**, **suppliers**, **projects**, and **bait files** (fake passwords, etc.).
Everything the AI writes must only mention things on this list.
