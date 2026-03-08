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

Coordinate across multiple skills to answer cross-cutting questions and handle multi-domain requests.

## When to Use This Skill

- User asks a temporal/summary question: "what happened last week?", "catch me up", "summary of today"
- User request touches 2+ skill domains: "I had a meeting with Alice and need to create a follow-up task"
- User asks about a person across domains: "what's going on with Alice?"

## When NOT to Use This Skill

- Request clearly maps to a single skill ("create a task", "write a journal entry")
- Those go directly to their respective skills

## Search

All skills are indexed as [QMD](https://github.com/tobi/qmd) collections. Use QMD for search:

**Search across all skills at once:**
```bash
qmd query --json "Alice"
```

**Search specific collections:**
```bash
qmd query -c journal -c meeting --json "project update"
qmd query -c backlog --json "Cloud Migration"
```

Results include `file` paths prefixed with `qmd://<collection>/` so you can tell which skill each result belongs to.

## Skill Registry

| Skill | QMD Collection | CLI Tool | Structured Query |
|-------|---------------|----------|-----------------|
| journal | `journal` | `python3 ~/.claude/skills/journal/journal_cli.py` | `query --date YYYY-MM-DD --tag TAG` |
| backlog | `backlog` | `python3 ~/.claude/skills/backlog/backlog_cli.py` | `query --status STATUS --project PROJECT`, `dashboard`, `stats` |
| meeting | `meeting` | `python3 ~/.claude/skills/meeting/meeting_cli.py` | `query --date YYYY-MM-DD --attendee NAME` |
| person | `person` | `python3 ~/.claude/skills/person/person_cli.py` | `search --name NAME --tag TAG`, `birthdays --month N` |

Use QMD for text/semantic search. Use CLIs for structured field-based queries (date ranges, status filters, attendee lookups, birthday months).

## Phase 1: Detect Mode

### Query Mode (read-only)

The user is asking about existing data across skills:
- "What happened last week?"
- "Catch me up"
- "Summary of today"
- "What's going on with Alice?"
- "What have I been working on?"

### Write Mode (multi-skill creation/update)

The user describes something that requires creating/updating entries in multiple skills:
- "I met Alice yesterday, we discussed the Cloud Migration project and she'll create a proposal by Friday"
- "Had a meeting with the team and need to reschedule the follow-up"

If ambiguous, ask: "Are you asking about existing data, or do you want me to create/update entries?"

## Phase 2a: Cross-Skill Query Workflow

**Never write files during query mode.**

### Step 1: Choose Search Strategy

**For text/topic/person queries** — use QMD across collections:
```bash
# Search everything at once
qmd query --json "Alice"

# Or target specific collections
qmd query -c meeting -c backlog --json "Cloud Migration"
```

**For structured/date queries** — use CLIs in parallel:
```bash
python3 ~/.claude/skills/journal/journal_cli.py query --date YYYY-MM
python3 ~/.claude/skills/meeting/meeting_cli.py query --date YYYY-MM
python3 ~/.claude/skills/backlog/backlog_cli.py query --due-after YYYY-MM-DD --due-before YYYY-MM-DD
```

**For dashboard/overview** — use backlog CLI:
```bash
python3 ~/.claude/skills/backlog/backlog_cli.py dashboard
```

### Step 2: Synthesize Results

Combine results based on query type:
- **Temporal queries** -- present as a chronological timeline, grouped by day
- **Person queries** -- group by interaction type (meetings, backlog items mentioning them)
- **Work queries** -- narrative combining journal entries and task activity

**Rules:**
- Never invent information not in search output
- If a skill returns no results, omit it from the response (don't say "no meetings found")
- If ALL skills return no results, say so clearly

## Phase 2b: Multi-Skill Write Workflow

### Step 1: Parse Intent

Extract all actionable items and map to skills:
- Meeting details -> **meeting** skill
- People mentioned -> **person** skill (for resolution)
- Follow-up actions/deadlines -> **backlog** skill
- Daily reflection -> **journal** skill

### Step 2: Confirm Plan

**Always** present the plan before executing. Format:

> I'll do the following:
> 1. [Skill]: [what will be created/updated]
> 2. [Skill]: [what will be created/updated]
>
> Does that look right?

Wait for user confirmation. Adjust if they correct anything.

### Step 3: Invoke Skills Sequentially via Skill Tool

After confirmation, invoke each skill using the Skill tool in this order:
1. **person** -- resolve names first (other skills may need the correct person reference)
2. **meeting** -- create meeting notes (also handles related journal entry)
3. **journal** -- only if a standalone journal entry is needed (not already covered by meeting)
4. **backlog** -- create follow-up tasks

Sequential because:
- Meeting needs resolved person names
- Tasks may reference meeting content
- Journal may be created by meeting skill already

### Step 4: Summary

Report what was created with file paths.

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Activating for single-skill requests | Only activate when multiple skills are needed |
| Writing files directly | Always delegate writes to individual skills via Skill tool |
| Skipping the confirmation step for writes | Always confirm the plan before invoking skills |
| Inventing information not in search output | Only present what QMD/CLIs return |
| Running write skills in parallel | Run sequentially -- writes may depend on each other |
