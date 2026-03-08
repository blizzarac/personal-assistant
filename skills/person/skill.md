---
name: person
description: Use when the user wants to create a new person entry, search/query existing people, or update person details. Trigger phrases include "person", "who is", "who did I meet", "birthdays", "add person", "update person", or providing a person's name with context.
---

# Person

**CLI:** `python3 ~/.claude/skills/person/person_cli.py`
**Data:** `~/.local/share/assistant/person/<Firstname Lastname>.md`
**QMD collection:** `person`

**Frontmatter:** `first_name`, `last_name`, `tags: [people]`, `birthday`, `how_we_met`, `last_meeting`, `father`, `mother`, `spouse`, `children`

## Detect Mode

- **Query mode** — "Who did I meet at Acme Corp?", "Birthdays in March"
- **Create mode** — "Sarah Chen, met at React conference"
- **Update mode** — "Update John Doe — last met today"

## Query Mode

Query mode is read-only — never write files.

Search: `qmd query -c person --json "React conference"`
Filters: `person_cli.py search --name "Jane" --tag "engineering" --how-we-met "conference"`
Birthdays: `person_cli.py birthdays --month 7`
Read: `person_cli.py read "Jane Smith.md"` or use the Read tool directly.

For family questions, follow `father`/`mother`/`children` links with additional reads.

## Create Mode

1. Extract name, how_we_met, birthday, tags from user input
2. Check for duplicates: `person_cli.py search --name "Sarah Chen"` — if match exists, confirm with user
3. Ask once: "Anything else? (birthday, tags, notes)"
4. Write `Firstname Lastname.md` with frontmatter
5. Run `qmd embed`

## Update Mode

1. Find: `person_cli.py search --name "John"`
2. Read file, apply changes via Edit tool (not full rewrite)
3. Run `qmd embed`

Convert relative dates: "today" → YYYY-MM-DD, "yesterday" → minus 1 day.
**Never** invent person info. Every person file must have `people` in tags.
