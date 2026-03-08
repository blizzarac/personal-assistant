---
name: backlog
description: Use when the user wants to create, update, query, or manage tasks. Trigger phrases include "backlog", "task", "to do", "what should I work on", "open tasks", "create a task", "close task", "task dashboard", "mark as done", "my priorities".
---

# Backlog

**CLI:** `python3 ~/.claude/skills/backlog/backlog_cli.py`
**Data:** `~/.local/share/assistant/backlog/<Project>/<Task>.md`
**QMD collection:** `backlog`

Tasks live in project subfolders. Simple tasks are single `.md` files; tasks with attachments use a folder (`Task/Task.md`).

**Frontmatter:** `tags: [tasks]`, `status: open|in-progress|done|blocked`, `project`, `priority`, `due_date`, `created_date`, `completed_date`, `description`

## Detect Mode

- **Query mode** — "Open tasks for MyProject", "Task dashboard", "What's due this week?"
- **Create mode** — "Create a task for...", "I need to..."
- **Update mode** — "Mark X as done", "Change priority of X"

## Query Mode

Query mode is read-only — never write files.

Search: `qmd query -c backlog --json "Cloud Migration"`
Filters: `backlog_cli.py query --status open --project MyProject --due-before 2026-03-01`
Dashboard: `backlog_cli.py dashboard`
Stats: `backlog_cli.py stats --project MyProject`
Projects: `backlog_cli.py list-projects`
Read: `backlog_cli.py read "MyProject/Task.md"` or use the Read tool directly.

## Create Mode

Extract title, project, priority, due date. Ask clarifying questions **one at a time**.

```
backlog_cli.py create --title "Task Name" --project MyProject --priority 5 --due-date 2026-03-01 --description "Summary"
```

For tasks with attachments, create `<Project>/<Task>/<Task>.md` manually.
Run `qmd embed` after creation.

## Update Mode

Search first. If multiple matches, confirm with user.

```
backlog_cli.py update "MyProject/Task.md" --status in-progress --priority 3
backlog_cli.py close "MyProject/Task.md"   # sets status=done + completed_date=today
```

Run `qmd embed` after any update.

## Migration

Move old flat-format task files into project subfolders:
```
backlog_cli.py migrate --dry-run   # preview
backlog_cli.py migrate             # execute
```

**Never** invent task content. **Always** search before creating to avoid duplicates.
