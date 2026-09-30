# AI Team — Tasks

Abdelrahman · Seif · Malak · Martina
Draft. Argue with it.

---

## Map

**Step 1 — Decide what the analyst sees on screen.**
That one answer decides which data the AI team needs.

**Step 2 — Build five pieces.**

- The data pipeline — Abdelrahman
- The fake content — Abdelrahman
- The model — Seif
- The explanations — Malak
- The measurement and the maze rule — Martina

**Step 3 — Agree three data formats with the cyber team.**
Then write the final report.

**The order is forced.**

```
Abdelrahman  →  Seif  →  Malak
   data          model     Martina
```

- Seif cannot train a model before Abdelrahman delivers clean data.
- Malak cannot explain a model that does not exist yet.
- Martina cannot measure a model that does not exist yet.

---

# 1. Decide

## What does the analyst watch on screen?

Nobody writes code until the team answers this. Every other task depends on the answer.

**Option A — the analyst watches network alerts.**

- The screen shows connections, ports, and traffic volume.
- CSE-CIC-IDS 2018 already fits this option. No new data needed.
- Work can start today.
- The system becomes an ordinary intrusion detector.
- The team drops the promise that the maze reads attacker skill.

**Option B — the analyst watches the attacker type.**

- The screen shows a live terminal: commands run, files opened, machines reached.
- This is the demo people picture when they hear the word maze.
- CSE-CIC-IDS 2018 cannot train this. That dataset holds no typed commands.
- The team adds a second dataset of recorded attacker sessions.
- Two datasets and two models means more work.

**Option C — the analyst watches the attacker, trained only on our own recordings.**

- Most realistic of the three.
- No such recordings exist until the Digital Twin is running.
- The AI team waits for the cyber team to finish building the decoys.

Owner: Abdelrahman.

---

# 2. Build

## Data pipeline — Abdelrahman

- Download CSE-CIC-IDS 2018.
- Count the real records. Chapter 1 used estimates.
- Delete the columns that name machines: IP addresses, ports, timestamps.
- Delete duplicate rows and impossible values.
- Choose which measurements the model keeps.
- Fix the imbalance. Almost every row is normal traffic.
- Ship one script that produces ready-to-train data.

Done when Seif runs one command and gets training data.

## Fake content — Abdelrahman

- Install Ollama and run Llama 3 on a project machine.
- Invent the fake company: departments, employees, headcount.
- Write one prompt per content type: email, HR file, finance sheet.
- Generate content for one department first.
- Check the fake content agrees with itself. Names and file paths must exist.
- Check no real person's data appears in the fake content.
- Give the finished content to the cyber team to load into the decoys.

Done when Philopateer explores the fake network and cannot tell the content is invented.

Every deception product on the market fills its traps with templates. This project writes
them with a language model. That is the part nobody else has.

## The model — Seif

- Compare two model types: ensemble models against sequence models.
- Split the data into a training set, a tuning set, and a final-test set.
- Train XGBoost first as a simple baseline.
- Train an LSTM to read command sequences.
- Combine both models into one.
- Make the model output a skill level, so the maze knows how deep to go.

The data pipeline deletes timestamps, so the data cannot be split by date.

## The explanations — Malak

- Compare two explanation tools, SHAP and LIME. Pick one.
- Attach the chosen tool to Seif's trained model.
- Decide what reason the analyst reads when the model flags someone.
- Show that reason on Mark's dashboard.

## The measurement and the maze rule — Martina

- Write down how the team will judge whether the model works.
- Design the maze rule: how attacker skill decides trap depth.
- Build the scripts that run the measurements.
- Measure false alarms, how long attackers stay trapped, and which attacks get caught.
- Run the full measurement once Seif's model is trained.
- Write the results report.

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

- **Abdelrahman** — get the team to answer the screen question in Section 1.
- **Abdelrahman** — download CSE-CIC-IDS 2018.
- **Abdelrahman** — fix the Phase 1 table of contents. Four bullets from Section 1.6 appear
  there as chapter headings.
- **Seif** — compare ensemble models against sequence models.
- **Malak** — compare SHAP against LIME.
- **Martina** — write the measurement plan.

Seif, Malak and Martina can all start today. Only Abdelrahman's tasks wait on the decision.
