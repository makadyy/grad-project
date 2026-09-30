# AI Team — Tasks

Abdelrahman · Seif · Malak · Martina
Draft. Argue with it.

---

## Map

**Section 1 — what Chapter 1 already decided.** Read it so nobody reopens a settled question.

**Section 2 — build five pieces.**

- The data pipeline — Abdelrahman
- The fake content — Abdelrahman
- The model — Seif
- The explanations — Malak
- The measurement and the maze rule — Martina

**Section 3 — agree three data formats with the cyber team.** Then write the final report.

**The order is forced.**

```
Abdelrahman  →  Seif  →  Malak
   data          model     Martina
```

- Seif cannot train a model before Abdelrahman delivers clean data.
- Malak cannot explain a model that does not exist yet.
- Martina cannot measure a model that does not exist yet.

---

# 1. Already decided

Chapter 1 answered these. Nobody reopens them.

- **Data.** Start with CSE-CIC-IDS 2018 network records. Add the project's own Digital Twin
  recordings later, as a separate real-world check.
- **Model.** XGBoost is required. LSTM only if time is left over.
- **Fake content.** Faker is required. Llama 3 only if the project machines can run it.
- **Maze.** Rule-based logic is required. Reinforcement learning is a later extension.
- **Split.** 70 / 15 / 15, balanced so every attack type appears in all three sets.

Each task below is marked **Must** or **Stretch** to match those decisions.

---

# 2. Build

## Data pipeline — Abdelrahman

- Download CSE-CIC-IDS 2018. **Must**
- Count the real records. Chapter 1 used estimates. **Must**
- Delete the columns that name machines: IP addresses, ports, timestamps. **Must**
- Delete duplicate rows and impossible values. **Must**
- Choose which measurements the model keeps. **Must**
- Fix the imbalance. Almost every row is normal traffic. **Must**
- Ship one script that produces ready-to-train data. **Must**

Done when Seif runs one command and gets training data.

## Fake content — Abdelrahman

- Build the Faker version first. Faker runs on any machine and needs no graphics card. **Must**
- Invent the fake company: departments, employees, headcount. **Must**
- Generate content for one department first. **Must**
- Check the fake content agrees with itself. Names and file paths must exist. **Must**
- Check no real person's data appears in the fake content. **Must**
- Give the finished content to the cyber team to load into the decoys. **Must**
- Add Llama 3 through Ollama on top, only if the project machines can run it. **Stretch**
- Write one prompt per content type: email, HR file, finance sheet. **Stretch**

Done when Philopateer explores the fake network and cannot tell the content is invented.

Faker produces believable names, dates and numbers. Llama 3 produces believable sentences.
The second one is what would make this project original, so try for it, but the project does
not fail without it.

## The model — Seif

- Compare ensemble models against sequence models on paper first. **Must**
- Split the data 70 / 15 / 15, balanced by attack type. **Must**
- Train XGBoost and validate it. **Must**
- Make the model output a skill level, so the maze knows how deep to go. **Must**
- Train an LSTM and compare it against XGBoost, only if time is left. **Stretch**

Do not start the LSTM until XGBoost is trained and measured.

## The explanations — Malak

- Compare two explanation tools, SHAP and LIME. Pick one. **Must**
- Attach the chosen tool to Seif's trained model. **Must**
- Decide what reason the analyst reads when the model flags someone. **Must**
- Show that reason on Mark's dashboard. **Must**

## The measurement and the maze rule — Martina

- Write down how the team will judge whether the model works. **Must**
- Design the maze rule: how attacker skill decides trap depth. **Must**
- Build the scripts that run the measurements. **Must**
- Measure false alarms, how long attackers stay trapped, and which attacks get caught. **Must**
- Run the full measurement once Seif's model is trained. **Must**
- Write the results report. **Must**

The maze rule is plain if-then logic. Reinforcement learning is a later extension, not part
of this work.

---

# 3. Connect

## Three data formats to agree with the cyber team

Chapter 1 is written, but no two people have agreed what data actually passes between them.
This is where projects like this usually break.

- **What the logging system sends the AI team.** Abdelrahman with Mohamed Salah.
- **How the model tells the system to cut off an attacker.** Martina with Mohamed Gamal.
- **What the model sends to the analyst's screen.** Malak with Mark.

## The final report

- The AI and method chapters — Abdelrahman and Seif.
- The results and explanation chapters — Malak and Martina.

---

# Start now

- **Abdelrahman** — download CSE-CIC-IDS 2018.
- **Abdelrahman** — check whether any project machine can run Llama 3.
- **Abdelrahman** — fix the Phase 1 table of contents. Four bullets from Section 1.6 appear
  there as chapter headings.
- **Seif** — compare ensemble models against sequence models.
- **Malak** — compare SHAP against LIME.
- **Martina** — write the measurement plan.

Nobody is blocked. All four can start today.
