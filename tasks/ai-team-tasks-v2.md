# AI Team — Tasks

Abdelrahman · Seif · Malak · Martina
Draft. Argue with it.

---

## Map

- One decision comes first.
- Then five build blocks, in a chain.
- Then two connection jobs.

**Who owns what**

- Abdelrahman — data and fake content
- Seif — the model
- Malak — explanations
- Martina — evaluation and maze

**The chain**

```
Abdelrahman  →  Seif  →  Malak
   data          model     Martina
```

- Seif waits for data.
- Malak and Martina wait for the model.
- If the front slips, everyone slips.

---

# 1. Decide

## The dataset question

Nobody codes until this is answered.

**The problem**

- Our dataset records network traffic.
- Our model must judge typed commands.
- Different data. Training will not transfer.

**Three options**

- Keep it. Shrink the claim.
- Add command-level data. Two sources.
- Use only our own logs. None exist yet.

Owner: Abdelrahman. Ask Dr. Sondos and Eng. Hemdan.

---

# 2. Build

## Data pipeline — Abdelrahman

- Download the dataset.
- Count records. Replace our estimates.
- Delete IPs, ports, timestamps.
- Remove duplicates and broken values.
- Build features. Cut correlated pairs.
- Fix imbalance. Training data only.
- Ship a script Seif can run.

Done when Seif runs one command and gets data.

## Fake content — Abdelrahman

- Install Ollama. Run Llama 3 offline.
- Invent the company. Departments, names, headcount.
- Write prompts per content type.
- Generate one department first.
- Check names and paths resolve.
- Screen for real personal data.
- Hand it to the cyber team.

Done when Philopateer cannot tell it is fake.

This is our original part. Everyone else uses templates.

## The model — Seif

- Compare ensemble against sequence models.
- Fix the split. Seeds. Leakage controls.
- Train the XGBoost baseline.
- Train the LSTM.
- Combine into one hybrid.
- Output a skill tier.

We deleted Timestamp. No time-based split.

## Explanations — Malak

- Compare SHAP and LIME. Pick one.
- Attach it to the trained model.
- Decide what the analyst sees.
- Wire into the dashboard with Mark.

## Evaluation and maze — Martina

- Draft the metrics framework.
- Design the maze policy. Skill in, depth out.
- Build the test harness.
- Add false positives, engagement time, ATT&CK coverage.
- Run the full evaluation.
- Write the performance report.

---

# 3. Connect

## To the cyber team

- Log format from the SIEM — Abdelrahman with Mohamed Salah.
- Containment trigger — Martina with Mohamed Gamal.
- Dashboard contract — Malak with Mark.

Nobody has agreed a format yet. This is where projects break.

## Final report

- AI and methodology — Abdelrahman and Seif.
- Evaluation and XAI — Malak and Martina.

---

# Start now

- Abdelrahman — ask about the dataset.
- Abdelrahman — download it.
- Abdelrahman — fix the TOC bug in Phase 1.
- Seif — compare architectures.
- Malak — compare SHAP and LIME.
- Martina — draft the metrics.

Three of us are not blocked. Only mine wait.

---

# For Kareem

- Ramez rejected Notion. He wants ClickUp.
- Section 1.6.6 has two owners. Martina and Seif.
- Labyrinth is an existing product name.
- Allocation says Martina Saeed. She said Khalil.
