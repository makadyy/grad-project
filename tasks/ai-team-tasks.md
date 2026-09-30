# AI Team — Main Tasks, Sub Tasks, Allocation

**Digital Twin Cyber Deception System (LabyrinthAI)** — AI track only
Abdelrahman Mohamed · Seif Mohamed · Malak Mahmoud · Martina Saeed

Draft for the team to confirm. Dates follow the official `Task_Assignment.pdf`
where they still hold, with September added because Phase 1 finished early.

---

## Where we are

- Chapter 1 submitted to Dr. Sondos on 31 August. All four of us contributed.
- No technical work has started. Nothing is coded, nothing is downloaded.
- `Task_Assignment.pdf` was written on 27 July and never updated. Its Phase 1
  starts 1 October, which is after the phase we already finished.
- That leaves September free. It is the only slack we get all year.

## One decision blocks everything

**Is CSE-CIC-IDS 2018 the right dataset?**

- It records **network traffic** — packet counts, byte counts, timings.
- Our classifier is meant to judge attacker skill from **what they do inside a decoy** —
  commands typed, files opened, how they move.
- Those are different kinds of data. A model trained on one does not transfer to the other.

Three ways out. Pick one before anyone writes code:

- **A** — Keep CSE-CIC-IDS 2018. Accept the classifier is a network intrusion detector.
  Drop "skill-adaptive" to something smaller and honest.
- **B** — Add command-level data: Cowrie honeypot logs, DARPA OpTC, or the LANL
  host/network dataset. Two data sources, two models.
- **C** — Train on our own session logs only. Highest realism, but nothing exists until
  the Digital Twin runs, so the AI team sits idle until Phase 2 ships.

**Owner: Abdelrahman. Needs Dr. Sondos and Eng. Hemdan. Target: 15 September.**

Everything below assumes this is settled first.

## The chain — why order matters

We are not four parallel workers. We are a queue.

```
Abdelrahman  →  Seif  →  Malak
   (data)      (model)   (XAI)
                  ↓
              Martina
            (evaluation)
```

- Seif cannot train until Abdelrahman delivers clean data.
- Malak cannot explain a model that does not exist.
- Martina cannot measure a model that does not exist.

If the front of the chain slips, everyone slips. That is the single biggest risk we carry.

---

## Main Task 1 — Data pipeline

**Owner: Abdelrahman** · Blocked by: the decision above · Due: 25 Oct 2026

| # | Sub task | Due |
|---|---|---|
| 1.1 | Download CSE-CIC-IDS 2018 and verify the files open | 20 Sep |
| 1.2 | Count real records and class distribution, replacing the estimates in 1.6.1 | 25 Sep |
| 1.3 | Strip identifier columns: IPs, ports, `Flow ID`, `Timestamp` | 05 Oct |
| 1.4 | Remove duplicates, repeated headers, `Infinity`/`NaN` | 05 Oct |
| 1.5 | Build feature engineering: keep behaviour, add the two ratios, cut correlated pairs | 15 Oct |
| 1.6 | Handle imbalance — undersample, SMOTE, class weights, training split only | 20 Oct |
| 1.7 | Ship a reproducible script plus a saved scaler Seif can call | 25 Oct |

**Definition of done:** Seif can run one command and get train/validation/test sets.

## Main Task 2 — LLM decoy generation

**Owner: Abdelrahman** · Blocked by: nothing · Due: 27 Dec 2026

| # | Sub task | Due |
|---|---|---|
| 2.1 | Install Ollama, run Llama 3 locally, confirm it works offline | 20 Sep |
| 2.2 | Design the fake company: departments, headcount, names, structure | 30 Sep |
| 2.3 | Write prompt templates per content type — email, HR file, finance sheet, memo | 15 Nov |
| 2.4 | Generate a first corpus for one department | 30 Nov |
| 2.5 | Build the consistency checker: names resolve, file paths resolve, no contradictions | 15 Dec |
| 2.6 | Screen output for real personal data and credential collisions | 20 Dec |
| 2.7 | Hand the corpus to the cyber team to load into the decoys | 27 Dec |

**Definition of done:** Philopateer explores the twin and cannot tell the content is fake.

**This is our most original component.** Every commercial deception product uses templates
or Faker. LLM-generated linked content is the part that is genuinely current research.

## Main Task 3 — Behavioural classifier

**Owner: Seif** · Blocked by: Task 1 · Due: 05 Feb 2027

| # | Sub task | Due |
|---|---|---|
| 3.1 | Compare architectures: ensemble versus sequence models | 25 Oct |
| 3.2 | Fix the split — ratio, stratification, seeds, leakage controls | 15 Jan |
| 3.3 | Train the XGBoost baseline | 25 Jan |
| 3.4 | Train the LSTM sequence model | 05 Feb |
| 3.5 | Combine into the hybrid classifier | 05 Feb |
| 3.6 | Define the skill-tier output the maze controller consumes | 05 Feb |

**Note:** 3.2 must match Section 1.6.3. We deleted `Timestamp`, so a time-based split is
not available. Agree this with Abdelrahman before writing it.

## Main Task 4 — Explainable AI

**Owner: Malak** · Blocked by: Task 3 · Due: 28 Mar 2027

| # | Sub task | Due |
|---|---|---|
| 4.1 | Compare SHAP and LIME for security decisions, pick one, write why | 01 Nov |
| 4.2 | Integrate onto the trained model | 10 Feb |
| 4.3 | Define what the analyst sees — which features, how ranked, how worded | 28 Feb |
| 4.4 | Attach explanations to dashboard events with Mark | 28 Mar |

## Main Task 5 — Evaluation and maze controller

**Owner: Martina** · Blocked by: Task 3 for evaluation, nothing for the controller · Due: 20 Apr 2027

| # | Sub task | Due |
|---|---|---|
| 5.1 | Draft the evaluation metrics framework | 01 Nov |
| 5.2 | Design the maze controller policy: skill tier in, trap depth out | 10 Feb |
| 5.3 | Build the test harness — accuracy, precision, recall, F1 scripts | 15 Feb |
| 5.4 | Add the metrics the allocation names: FPR, engagement time, ATT&CK coverage | 28 Feb |
| 5.5 | Run the full evaluation with Seif and Malak | 15 Apr |
| 5.6 | Produce the final performance report | 20 Apr |

## Main Task 6 — Interfaces with the cyber team

**Owner: shared** · Due: 15 Nov 2026

| # | Sub task | Owner | Due |
|---|---|---|---|
| 6.1 | Agree the log format the SIEM sends us — with Mohamed Salah | Abdelrahman | 30 Oct |
| 6.2 | Agree how the maze controller triggers containment — with Mohamed Gamal | Martina | 15 Nov |
| 6.3 | Agree the dashboard contract — with Mark | Malak | 15 Nov |

**Why this exists.** Chapter 1 is written but no two people have agreed an actual data
format. This is where integration projects usually break.

## Main Task 7 — Final report

**Owner: shared** · Due: 10 May 2027

| # | Sub task | Owner |
|---|---|---|
| 7.1 | AI and methodology sections | Abdelrahman + Seif |
| 7.2 | Evaluation and XAI sections | Malak + Martina |

---

## This week

| Task | Owner |
|---|---|
| Take the dataset question to Dr. Sondos and Eng. Hemdan | Abdelrahman |
| Fix the TOC bug in `Phase 1.docx` — the decoy bullets are styled as headings | Abdelrahman |
| Download CSE-CIC-IDS 2018 | Abdelrahman |
| Install Ollama and Llama 3 | Abdelrahman |
| Start the SHAP versus LIME comparison | Malak |
| Start the metrics framework draft | Martina |
| Start the architecture comparison | Seif |

Malak, Martina and Seif can all start their research tasks now. None of them need data.

## For Kareem

- **Tooling.** Eng. Ramez said on 19 August that Notion is no good and pushed ClickUp or
  Trello. Decide before we build the board twice.
- **Ownership clash.** `Task_Assignment.pdf` makes Martina Evaluation Lead. The WhatsApp
  split gave Section 1.6.6 Evaluation Metrics to Seif. One of the two is wrong.
- **Name.** There is a commercial deception platform called Labyrinth. Worth settling
  before anyone presents.
- **Name on file.** The allocation lists Martina Saeed. She corrected this in the group on
  27 July to Martina Khalil. It is on a document going to the Dean.
