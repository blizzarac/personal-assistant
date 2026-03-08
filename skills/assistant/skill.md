---
name: assistant
description: >
  Use when a request spans multiple skills or asks for a cross-cutting
  summary. Trigger phrases include "what happened last week", "catch me up",
  "summary of today", "overview", or when the request mentions multiple
  domains (e.g. meetings and backlog, journal and people). Do NOT use for
  single-domain requests like "create a task" or "write a journal entry"
  — those go directly to their respective skills.
---

# Assistant

Coordinate across skills for cross-cutting queries and multi-domain writes.

**Only activate** when the request touches 2+ skills or asks for a temporal summary. Single-domain requests ("create a task") go directly to their skill.

## Search

All skills use [QMD](https://github.com/tobi/qmd) collections:

```bash
qmd query --json "Alice"                              # search all collections
qmd query -c journal -c meeting --json "project update" # specific collections
```

For structured/date queries, run CLIs in parallel:
```bash
journal_cli.py query --date YYYY-MM
meeting_cli.py query --date YYYY-MM --attendee NAME
backlog_cli.py query --status open --due-before YYYY-MM-DD
backlog_cli.py dashboard
calendar_cli.py events --date YYYY-MM-DD --days 7
```

CLIs live at `~/.claude/skills/<skill>/<skill>_cli.py`.

## Query Mode

Never write files. Choose strategy:
- **Text/topic/person** → QMD across collections
- **Date-based** → CLIs in parallel
- **Overview** → `backlog_cli.py dashboard`

Synthesize results:
- Temporal → chronological timeline by day
- Person → group by interaction type
- Work → narrative of journal + tasks

Omit skills with no results. Never invent information.

## Write Mode

When the user describes something spanning multiple skills:

1. **Parse intent** → map to skills (calendar, meeting, person, backlog, journal)
2. **Confirm plan** before executing:
   > I'll do: 1. [Skill]: [action] 2. [Skill]: [action]. Does that look right?
3. **Invoke skills sequentially** via Skill tool: person → meeting → journal → backlog → calendar
4. **Report** what was created

Sequential because: meetings need resolved names, tasks may reference meetings, journal may already be created by meeting skill.

**Never** write files directly — delegate to individual skills. **Never** skip confirmation for writes.
