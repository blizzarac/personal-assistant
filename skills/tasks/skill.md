---
name: tasks
description: Use when the user wants to create, update, query, or manage tasks. Trigger phrases include "task", "tasks", "to do", "what should I work on", "open tasks", "create a task", "close task", "task dashboard", "mark as done", "my priorities".
---

# Tasks

Manage tasks: create, update, query, and get overviews.

**CLI tool:** `python3 ~/.claude/skills/tasks/task_cli.py <command> [args]`
**Config:** `~/.claude/skills/tasks/config.yaml`
**Tasks directory:** Configured in config.yaml (default: ~/.local/share/assistant/tasks)

## Notes Structure

```
<data_dir>/
  Project/
    Task Name.md                    # simple task
    Complex Task/                   # folder-style task
      Complex Task.md
      screenshot.png
  _unassigned/
    Task without project.md
  .index.md
```

Tasks are organized by project. Simple tasks are single files; tasks with attachments use a folder.

**Frontmatter:**
```yaml
---
links:
tags:
  - tasks
status: open          # open | in-progress | done | blocked
inform:
outcome:
project: MyProject
Priority:
due_date:
created_date: YYYY-MM-DD
completed_date:
description: One-line summary
---
```

**Body:** Freeform notes, details, or acceptance criteria.

## Phase 1: Refresh Index

On every invocation, run:
```
python3 ~/.claude/skills/tasks/task_cli.py refresh
```
Returns JSON: `{added, removed, total}`. Only mention changes to the user if relevant.

## Phase 2: Detect Mode

**Query mode** — The user is asking about existing tasks:
- "Show me open tasks for MyProject"
- "What's my highest priority task?"
- "What tasks are due this week?"
- "How many tasks did I close this month?"
- "Task dashboard"

**Create mode** — The user wants to create a new task:
- "Create a task for..."
- "I need to..."
- "Add a task..."

**Update mode** — The user wants to modify an existing task:
- "Mark X as done"
- "Change priority of X to 5"
- "Block the Database Migration task"
- "Close the Cloud Migration task"

If ambiguous, ask: "Do you want to create a new task, update an existing one, or search your tasks?"

## Phase 3a: Query Mode (Read-Only)

**Never write files during query mode.**

Use CLI commands:

**Filter tasks:**
```
python3 ~/.claude/skills/tasks/task_cli.py query --status open
python3 ~/.claude/skills/tasks/task_cli.py query --status open --project MyProject
python3 ~/.claude/skills/tasks/task_cli.py query --search "Cloud Migration"
python3 ~/.claude/skills/tasks/task_cli.py query --due-before 2026-03-01
python3 ~/.claude/skills/tasks/task_cli.py query --priority 1
```
Filters can be combined. Returns `{results, count}`.

**Dashboard overview:**
```
python3 ~/.claude/skills/tasks/task_cli.py dashboard
```
Returns projects with counts, top tasks, overdue, due soon, and summary.

**Statistics:**
```
python3 ~/.claude/skills/tasks/task_cli.py stats
python3 ~/.claude/skills/tasks/task_cli.py stats --project MyProject
```

**List projects:**
```
python3 ~/.claude/skills/tasks/task_cli.py list-projects
```

**Read a specific task:**
```
python3 ~/.claude/skills/tasks/task_cli.py read "MyProject/API Integration.md"
```

Present results as markdown tables or narrative depending on the question.

## Phase 3b: Create Mode

Extract title, project, priority, due date from user input. Ask clarifying questions **one at a time** if needed.

```
python3 ~/.claude/skills/tasks/task_cli.py create --title "Task Name" --project MyProject --priority 5 --due-date 2026-03-01 --description "One-line summary"
```

If user mentions attachments or supporting files, create a folder-style task manually:
1. Create directory: `tasks/<project>/<Task Name>/`
2. Create `tasks/<project>/<Task Name>/<Task Name>.md` with frontmatter

Run `refresh` after creation.

## Phase 3c: Update Mode

Search for the task first. If multiple matches, confirm which one with the user.

**Update fields:**
```
python3 ~/.claude/skills/tasks/task_cli.py update "MyProject/Task Name.md" --status in-progress
python3 ~/.claude/skills/tasks/task_cli.py update "MyProject/Task Name.md" --priority 3
python3 ~/.claude/skills/tasks/task_cli.py update "MyProject/Task Name.md" --due-date 2026-04-01
```

**Mark as done (shortcut):**
```
python3 ~/.claude/skills/tasks/task_cli.py close "MyProject/Task Name.md"
```
Auto-fills `completed_date` with today.

Run `refresh` after any update.

## Phase 4: Refresh Index

After any write operation (create, update, close), run:
```
python3 ~/.claude/skills/tasks/task_cli.py refresh
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Writing files during query mode | Query mode is read-only |
| Reading index files directly | Use CLI commands instead |
| Asking multiple questions at once | One question per message during create mode |
| Not running refresh after writes | Always refresh after create/update/close |
| Creating duplicate tasks | Search first before creating |
| Updating wrong task on ambiguous match | Always confirm with user if multiple matches |
| Inventing task content | Only use what the user provided |
