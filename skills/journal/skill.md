---
name: journal
description: Use when the user wants to write a journal entry, ask about past journal entries, or get summaries of what happened in a time period. Trigger phrases include "journal", "how was my day", "journal entry", "what did I do last week", or describing their day.
---

# Journal

**CLI:** `python3 ~/.claude/skills/journal/journal_cli.py`
**Data:** `~/.local/share/assistant/journal/YYYY/YYYY-MM-DD-DayOfWeek-Journal.md`
**QMD collection:** `journal`

One file per day. Multiple entries on the same day are appended separated by `---`.

**Frontmatter:** `tags: [journal]`, `date: YYYY-MM-DD`, `description: One-line summary`

## Detect Mode

- **Write mode** — "Journal entry", describing their day
- **Query mode** — "What did I do last week?", "When did I go fishing?"

## Query Mode

Query mode is read-only — never write files.

Search: `qmd query -c journal --json "fishing trip"`
Date filter: `journal_cli.py query --date "2025-09" --tag "work"`
Read: `journal_cli.py read "2025/2025-09-06-Saturday-Journal.md"` or use the Read tool directly.

## Write Mode

Ask follow-up questions **one at a time**. Then:

1. Check if `YYYY/YYYY-MM-DD-DayOfWeek-Journal.md` already exists for the target date
2. **Exists** — append new content after `---`, update `description`
3. **New** — create file with frontmatter + structured content
4. Run `qmd embed`

**Never** create a second file for the same day — always append.
**Never** invent content — only write what the user said.
