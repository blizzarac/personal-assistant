---
name: meeting
description: Use when the user wants to create meeting notes, search past meetings, or query meetings by person/topic/date. Trigger phrases include "meeting", "meeting notes", "I had a meeting", "meetings with", "what meetings", or describing a meeting that happened.
---

# Meeting Notes

Create structured meeting notes and link them to the journal.

**CLI tool:** `python3 ~/.claude/skills/meeting/meeting_cli.py <command> [args]`
**Config:** `~/.claude/skills/meeting/config.yaml`
**Meetings directory:** Configured in config.yaml (default: ~/.local/share/assistant/meeting/YYYY/)

## Notes Structure

```
<data_dir>/
  YYYY/
    Title (YYYY-MM-DD).md
    Title (YYYY-MM-DD).md
    ...
  .meetings-index.md
```

Meetings are organized by year. Each meeting is a single markdown file named `<Title> (YYYY-MM-DD).md`.

**Frontmatter:**
```yaml
---
tags:
  - meetings
date: YYYY-MM-DD
links:
attendees:
  - "[[Person Name]]"
scheduling: Ad hoc
---
```

**Body sections** (only include sections with content):
- `## Topics` — what was discussed
- `## Decisions` — what was decided
- `## Action Items` — what needs to happen next, with owners

## Phase 1: Refresh Index

On every invocation, run:
```
python3 ~/.claude/skills/meeting/meeting_cli.py refresh
```
Returns JSON: `{added, removed, total}`. Only mention changes to the user if relevant.

## Phase 2: Detect Mode

**Create mode** — The user is describing a meeting:
- "Meeting with Alice about Cloud Migration"
- "I had a meeting today..."
- Raw notes pasted with meeting context

**Query mode** — The user is asking about past meetings:
- "What meetings did I have with Alice?"
- "Meetings about Cloud Migration"
- "Summarize meetings from October"

If ambiguous, ask: "Do you want to create meeting notes, or search past meetings?"

## Phase 3a: Query Mode (Read-Only)

**Never write files during query mode.**

Use CLI commands:

**Search by attendee, date, or topic:**
```
python3 ~/.claude/skills/meeting/meeting_cli.py query --attendee "Alice"
python3 ~/.claude/skills/meeting/meeting_cli.py query --date "2025-09"
python3 ~/.claude/skills/meeting/meeting_cli.py query --search "Cloud Migration"
```

**Read a specific meeting for detail:**
```
python3 ~/.claude/skills/meeting/meeting_cli.py read "2025/Team Sync (2025-09-11).md"
```

Present results as markdown table or narrative depending on query type.

## Phase 3b: Create Mode

### Step 1: Gather input
Extract from user's notes: title, date (default: today), attendees, scheduling, links.
If title is not obvious, ask: "What should I call this meeting?"

### Step 2: Resolve attendees
Use person CLI to find correct names:
```
python3 ~/.claude/skills/person/person_cli.py search --name "Alice"
```
Format as `"[[Firstname Lastname]]"` in the attendees array.

### Step 3: Structure content
Organize raw notes into sections (only include sections with content):
- **Topics** — what was discussed
- **Decisions** — what was decided
- **Action Items** — what needs to happen next

### Step 4: Create meeting file

**Directory:** YYYY/ — create if it doesn't exist.
**Filename:** `<Title> (YYYY-MM-DD).md`

**Format:**
```markdown
---
tags:
  - meetings
date: YYYY-MM-DD
links:
attendees:
  - "[[Person Name]]"
scheduling: Ad hoc
---

## Topics
- [structured from raw notes]

## Decisions
- [if any]

## Action Items
- [if any, with owners]
```

### Step 5: Create or append journal entry

Follow the journal skill pattern for the same date:
1. Check if YYYY/YYYY-MM-DD-DayOfWeek-Journal.md exists in the journal data directory (configured in meeting's config.yaml as journal_data_dir)
2. If exists — append meeting summary under `## Meetings` section
3. If not — create a minimal journal entry with the meeting link

### Step 6: Update indexes

Run both:
```
python3 ~/.claude/skills/meeting/meeting_cli.py refresh
python3 ~/.claude/skills/journal/journal_cli.py refresh
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Writing files during query mode | Query mode is read-only |
| Reading index files directly | Use `query` or `refresh` commands instead |
| Not resolving attendee names | Always check the people index via person CLI |
| Inventing meeting content | Only structure what the user provided |
| Wrong filename format | Always use `<Title> (YYYY-MM-DD).md` |
| Forgetting journal entry | Every meeting must also create/update a journal entry |
| Not updating both indexes | Both meetings and journal indexes must be refreshed |
