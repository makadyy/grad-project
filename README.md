# Grad Project — LabyrinthAI (Digital Twin Cyber Deception System)

You (Abdelrahman) are the **AI track lead**: data pipeline + fake-content generation,
on a team with Seif (model), Malak (explanations/XAI), Martina (measurement + maze rule).

Order is forced: **you → Seif → Malak/Martina** (they can't work until your data/model exist).

## What's already decided (Chapter 1, don't reopen)
- Data: CSE-CIC-IDS 2018 network records + the project's own Digital Twin recordings later.
- Model: XGBoost required, LSTM only if time allows.
- Fake content: Faker required, Llama 3 only if the project machines can run it.
- Open question flagged in `tasks/ai-team-tasks.md`: whether CSE-CIC-IDS 2018 (network
  traffic) actually matches the "attacker skill from in-decoy behavior" goal — read the
  "One decision blocks everything" section there before writing code.

## Folder map
| Folder | What's in it |
|---|---|
| `chapter-1/` | Your submitted Chapter 1 section (1.6, AI/data). `v6-share.md` is the version shared with the team; `v1`–`v6` are drafts. |
| `tasks/` | Team task breakdown docs, v1→v4 (`ai-team-tasks-v4.md` is latest). Also `Task_Assignment.pdf` (official, dated, partly stale — see notes in the tasks doc). |
| `mockups/` | Empty — nothing dropped here yet. |
| `whatsapp-data/` | Everything pulled out of the team WhatsApp export. See below. |
| `_inbox/` | Drop zone — put a fresh WhatsApp export `.zip` (or any new doc) here and ask me to process it; see `_inbox/README.md`. |
| `.claude/`, `.gstack/`, `.remember/` | Tooling, not project content. Ignore. |

### `whatsapp-data/`
- `documents/` — **actual useful files**, extracted and converted to text: the graduation
  project proposal, allocation doc, thesis template, task assignment PDF, "Phase 1" doc, etc.
  Start here if you need a specific document's content.
- `voice-notes/` — transcribed voice notes from the group chat.
- `_raw`, `_raw2`, `_raw3`, `_raw4` — successive raw exports of the chat (each re-export
  after the chat grew further). `_raw4` is the most complete. Left untouched for now since
  `documents/`/`voice-notes/` already hold the extracted useful content.
- `_archive/` — old Google Drive download zip + its manually-extracted copy (`w-media/`).
  Redundant with `_raw*`, kept only in case something was missed; safe to delete later.

## Cleanup done just now
- Moved the loose `drive-download-*.zip` and `w media/` folder (leftover duplicates of
  what's already in `whatsapp-data/_raw`) into `whatsapp-data/_archive/`.
- Nothing was deleted — only relocated, since a couple of the "duplicate-looking" zips
  turned out to have different hashes (different export timestamps), not identical copies.
- Left `_inbox/` and the `_raw*` folders alone — they're an existing intentional pipeline
  (see `_inbox/README.md`), not clutter.

## Next honest step
Nothing technical has started (per `tasks/ai-team-tasks.md`). The one decision blocking
everything is the dataset-mismatch question above — resolve that, then start the data
pipeline.
