---
name: person
description: Use when the user wants to create a new person entry, search/query existing people, or update person details. Trigger phrases include "person", "who is", "who did I meet", "birthdays", "add person", "update person", or providing a person's name with context.
---

# Person

Manage the people directory: create new person entries, query/search people, and update existing entries.

**CLI tool:** `python3 ~/.claude/skills/person/person_cli.py <command> [args]`
**Config:** `~/.claude/skills/person/config.yaml`
**People directory:** Configured in config.yaml (default: ~/.local/share/assistant/person)

## Notes Structure

```
<data_dir>/
  Firstname Lastname.md
  Firstname Lastname.md
  ...
  .index.md
```

Each person is a single markdown file in the root of the data directory. The index also includes a birthday calendar.

**Frontmatter:**
```yaml
---
first_name: Jane
last_name: Smith
tags:
  - people
birthday: YYYY-MM-DD
how_we_met: Tech conference 2025
last_meeting: YYYY-MM-DD
father:
mother:
spouse:
children:
---
```

**Body:** Freeform notes about the person.

## Phase 1: Refresh Index

On every invocation, run:
```
python3 ~/.claude/skills/person/person_cli.py refresh
```
Returns JSON: `{added, removed, total}`. This also rebuilds the birthday calendar. Only mention changes to the user if relevant.

## Phase 2: Detect Mode

**Update mode** — Input contains "update" + a person's name:
- "Update John Doe — last met today"
- "Update John birthday to 2022-07-15"

**Query mode** — Input contains a question or search term:
- "Who did I meet at Acme Corp?"
- "Birthdays in March"
- "Who is tagged with engineering?"

**Create mode** — Input contains a name with descriptive info:
- "Sarah Chen, met at React conference"

If ambiguous, ask: "Do you want to create a new person entry, search for someone, or update an existing entry?"

## Phase 3a: Query Mode (Read-Only)

**Never write files during query mode.**

Use CLI commands:

**Search by name, tag, or how-we-met:**
```
python3 ~/.claude/skills/person/person_cli.py search --name "Jane"
python3 ~/.claude/skills/person/person_cli.py search --tag "engineering"
python3 ~/.claude/skills/person/person_cli.py search --how-we-met "tech conference"
```

**Birthdays:**
```
python3 ~/.claude/skills/person/person_cli.py birthdays --month 7
```

**Read a specific person for detail (relationships, body content):**
```
python3 ~/.claude/skills/person/person_cli.py read "Jane Smith.md"
```

### Relationship Traversal
For family questions, use `read` to get the person file, then follow `father`/`mother`/`children` links with additional `read` calls.

### Response Format
- **Multi-person results:** Markdown table with relevant columns
- **Single-person lookup:** Summary card showing all populated fields

## Phase 3b: Create Mode

1. **Parse input** — Extract name, how_we_met, birthday, tags from user message
2. **Check for duplicates:**
   ```
   python3 ~/.claude/skills/person/person_cli.py search --name "Sarah Chen"
   ```
   If a match exists, ask: "A person named [Name] already exists. Did you mean to update them?"
3. **Fill gaps** — Ask once: "Anything else you want to add? (birthday, location, tags, notes)"
4. **Create file** — Write `Firstname Lastname.md` with frontmatter.
5. **Update index** — Run `refresh` to pick up the new file.

## Phase 3c: Update Mode

1. **Find the person:**
   ```
   python3 ~/.claude/skills/person/person_cli.py search --name "John"
   ```
2. **Read the file** for current state
3. **Apply changes** via the Edit tool (not full file rewrite)
4. **Update index** — Run `refresh`

## Date Handling

Convert relative dates to actual dates:
- "today" → current date (YYYY-MM-DD)
- "yesterday" → current date minus 1 day
- "March 5" → YYYY-03-05 (current year)

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Writing files during query mode | Query mode is read-only |
| Reading the index file directly | Use `search`, `birthdays`, or `refresh` commands instead |
| Creating duplicate person files | Always check with `search --name` before creating |
| Overwriting body content on update | Use Edit tool to modify specific fields, not full rewrite |
| Missing `people` tag | Every person file must have `people` in tags |
| Inventing person info | Only report what is in the files — never fabricate details |
