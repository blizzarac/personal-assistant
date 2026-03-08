---
name: meeting
description: Use when the user wants to create meeting notes, search past meetings, or query meetings by person/topic/date. Trigger phrases include "meeting", "meeting notes", "I had a meeting", "meetings with", "what meetings", or describing a meeting that happened.
---

# Meeting Notes

**CLI:** `python3 ~/.claude/skills/meeting/meeting_cli.py`
**Data:** `~/.local/share/assistant/meeting/YYYY/<Title> (YYYY-MM-DD).md`
**QMD collection:** `meeting`

**Frontmatter:** `tags: [meetings]`, `date`, `attendees: ["[[Name]]"]`, `scheduling: Ad hoc`
**Body sections** (only if content): `## Topics`, `## Decisions`, `## Action Items`

## Detect Mode

- **Create mode** — "Meeting with Alice about X", "I had a meeting today..."
- **Query mode** — "What meetings did I have with Alice?", "Meetings about X"

## Query Mode

Query mode is read-only — never write files.

Search: `qmd query -c meeting --json "Cloud Migration"`
Filters: `meeting_cli.py query --date "2025-09" --attendee "Alice"`
Read: `meeting_cli.py read "2025/Team Sync (2025-09-11).md"` or use the Read tool directly.

## Create Mode

1. Extract title, date (default: today), attendees, scheduling from user input
2. Resolve attendees via `person_cli.py search --name "Alice"` → format as `"[[Firstname Lastname]]"`
3. Structure raw notes into Topics/Decisions/Action Items sections
4. Create `YYYY/<Title> (YYYY-MM-DD).md` with frontmatter + body
5. Run `qmd embed`
6. Create or append journal entry for the same date (check journal data dir from config.yaml `journal_data_dir`)

**Never** invent meeting content — only structure what the user provided.
**Always** resolve attendee names against the people directory.
