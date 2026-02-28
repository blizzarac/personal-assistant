---
name: assistant
description: >
  Use when a request spans multiple skills or asks for a cross-cutting
  summary. Trigger phrases include "what happened last week", "catch me up",
  "summary of today", "overview", or when the request mentions multiple
  domains (e.g. meetings and tasks, journal and people). Do NOT use for
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

## Skill Registry

| Skill | Domain | CLI Tool | Query/Search Command | Date Filter |
|-------|--------|----------|---------------------|-------------|
| journal | Daily entries and reflections | `python3 ~/.claude/skills/journal/journal_cli.py` | `query --date YYYY-MM-DD --search TEXT` | `--date` (prefix: YYYY, YYYY-MM, YYYY-MM-DD) |
| tasks | Task management, projects, priorities, due dates | `python3 ~/.claude/skills/tasks/task_cli.py` | `query --status STATUS --project PROJECT --search TEXT` | `--due-before YYYY-MM-DD`, `--due-after YYYY-MM-DD` |
| meeting | Meeting notes, attendees, topics | `python3 ~/.claude/skills/meeting/meeting_cli.py` | `query --date YYYY-MM-DD --attendee NAME --search TEXT` | `--date` (prefix: YYYY, YYYY-MM, YYYY-MM-DD) |
| person | People directory, relationships, birthdays | `python3 ~/.claude/skills/person/person_cli.py` | `search --name NAME --tag TAG` | No date filter |

### Additional CLI Commands

- **tasks:** `dashboard` (overview by project), `stats`, `list-projects`
- **person:** `birthdays --month N`
- **All skills with CLIs:** `read <file>` to read a specific entry

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

### Step 1: Determine Relevant Skills

Map the request to skills:

| Request Type | Skills to Query |
|-------------|----------------|
| "What happened last week/today?" | journal, meeting, tasks |
| "What's going on with [person]?" | person, meeting, tasks |
| "What have I been working on?" | journal, tasks |
| "Catch me up" | journal, meeting, tasks |

### Step 2: Query CLIs in Parallel

Call all relevant CLI tools in parallel using the Bash tool. Examples:

**Temporal query ("last week", given today is YYYY-MM-DD, compute date range accordingly):**
```bash
python3 ~/.claude/skills/journal/journal_cli.py query --date YYYY-MM
python3 ~/.claude/skills/meeting/meeting_cli.py query --date YYYY-MM
python3 ~/.claude/skills/tasks/task_cli.py query --due-after YYYY-MM-DD --due-before YYYY-MM-DD
```

**Person query ("what's going on with Alice"):**
```bash
python3 ~/.claude/skills/person/person_cli.py search --name "Alice"
python3 ~/.claude/skills/meeting/meeting_cli.py query --attendee "Alice"
python3 ~/.claude/skills/tasks/task_cli.py query --search "Alice"
```

**Today's summary (given today is YYYY-MM-DD):**
```bash
python3 ~/.claude/skills/journal/journal_cli.py query --date YYYY-MM-DD
python3 ~/.claude/skills/meeting/meeting_cli.py query --date YYYY-MM-DD
python3 ~/.claude/skills/tasks/task_cli.py dashboard
```

### Step 3: Synthesize Results

Combine results based on query type:
- **Temporal queries** -- present as a chronological timeline, grouped by day
- **Person queries** -- group by interaction type (meetings, tasks mentioning them)
- **Work queries** -- narrative combining journal entries and task activity

**Rules:**
- Never invent information not in CLI output
- If a skill returns no results, omit it from the response (don't say "no meetings found")
- If ALL skills return no results, say so clearly

## Phase 2b: Multi-Skill Write Workflow

### Step 1: Parse Intent

Extract all actionable items and map to skills:
- Meeting details -> **meeting** skill
- People mentioned -> **person** skill (for resolution)
- Follow-up actions/deadlines -> **tasks** skill
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
4. **tasks** -- create follow-up tasks

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
| Querying via Skill tool instead of CLI | Use CLI directly for reads -- faster and simpler |
| Inventing information not in CLI output | Only present what the CLIs return |
| Running write skills in parallel | Run sequentially -- writes may depend on each other |
| Using wrong date filter for tasks | Tasks use `--due-before`/`--due-after`, not `--date` |
