---
name: journal
description: Use when the user wants to write a journal entry, ask about past journal entries, or get summaries of what happened in a time period. Trigger phrases include "journal", "how was my day", "journal entry", "what did I do last week", or describing their day.
---

# Journal

Manage the user's journal: create new entries and query journal history.

**CLI tool:** `python3 ~/.claude/skills/journal/journal_cli.py <command> [args]`
**Config:** `~/.claude/skills/journal/config.yaml`
**Journal directory:** Configured in config.yaml (default: ~/.local/share/assistant/journal)
**Search:** Uses [QMD](https://github.com/tobi/qmd) collection `journal` for semantic search.

## Notes Structure

```
<data_dir>/
  YYYY/
    YYYY-MM-DD-DayOfWeek-Journal.md
    YYYY-MM-DD-DayOfWeek-Journal.md
    ...
```

One file per day. If multiple entries are written on the same day, they are appended to the existing file separated by `---`.

**Frontmatter:**
```yaml
---
tags:
  - journal
date: YYYY-MM-DD
description: One-line summary of the day
---
```

**Body:** Freeform structured content from conversation.

## Phase 1: Refresh Search Index

On every invocation, run:
```
qmd embed
```
This re-indexes all QMD collections. Only mention this to the user if relevant.

## Phase 2: Detect Mode

**Write mode** — The user wants to create a new journal entry:
- "Journal entry", "Let me tell you about my day"
- Describing events, feelings, activities

**Query mode** — The user is asking about past entries:
- "What did I do last week?", "Summarize this month"
- "When did I go fishing?"

If ambiguous, ask: "Do you want to write a journal entry, or are you looking for a summary of past entries?"

## Phase 3a: Query Mode

**Never write files during query mode.**

**Search journal entries with QMD:**
```bash
qmd query -c journal --json "fishing trip"
qmd search -c journal --json "morning routine"
```
Use `query` for semantic/hybrid search, `search` for keyword-only.

**Date-based queries:** Use the CLI for structured date filtering:
```
python3 ~/.claude/skills/journal/journal_cli.py query --date "2025-09"
python3 ~/.claude/skills/journal/journal_cli.py query --tag "work"
```

**Read a specific entry for detail:**
```
python3 ~/.claude/skills/journal/journal_cli.py read "2025/2025-09-06-Saturday-Journal.md"
```

Or read the file directly with the Read tool.

Present results in the appropriate format:
- **Time-based** — narrative of key events from that period
- **Search** — show matching entries from QMD results

## Phase 3b: Write Mode

Conversational flow — ask questions **one at a time**:

1. **Start** — If the user already described their day, acknowledge and ask follow-ups. If not, ask "How was your day?"
2. **Follow-ups** — Ask naturally about things not yet covered.

Then write the entry:

**IMPORTANT: One entry per day.** Before creating a new file, always check if a file already exists for that date.

### Check for existing file

Look for a file matching today's date (or the target date) in the year folder:
- Check for `YYYY/YYYY-MM-DD-DayOfWeek-Journal.md`

### If a file already exists — APPEND

1. Read the existing file
2. Append the new content at the end of the file, separated by a horizontal rule (`---`)
3. Update the frontmatter `description` to cover the full day

### If no file exists — CREATE

**Filename:** `YYYY/YYYY-MM-DD-DayOfWeek-Journal.md`

**Format:**
```markdown
---
tags:
  - journal
date: YYYY-MM-DD
description: One-line summary of the day
---

[Freeform structured content from conversation.]
```

## Phase 4: Update Search Index

After creating/modifying a journal entry, run:
```
qmd embed
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Writing files during query mode | Query mode is read-only |
| Asking multiple questions at once | One question per message during write mode |
| Creating a second file for the same day | Always check if today's file exists first — append to it |
| Wrong filename format | New entries use `YYYY-MM-DD-DayOfWeek-Journal.md` |
| Inventing journal content | Only report what is in the files — never fabricate events or feelings |
