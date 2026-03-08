---
name: calendar
description: Use when the user wants to check their calendar, see upcoming events, create calendar events, or ask about scheduled meetings/appointments. Trigger phrases include "calendar", "schedule", "what's on my calendar", "free time", "book a meeting", "create an event", "upcoming events", "what do I have today", "am I free on".
---

# Calendar

**CLI:** `python3 ~/.claude/skills/calendar/calendar_cli.py`
**Data:** `~/.local/share/assistant/calendar/YYYY/<Title> (YYYY-MM-DD).md`
**QMD collection:** `calendar`

Events are synced from Google Calendar to local markdown for QMD search.

**Frontmatter:** `tags: [calendar]`, `date`, `end_date`, `calendar`, `status`, `event_id`, `location`, `attendees`

## Setup

Requires `pip install google-api-python-client google-auth-oauthlib`. User must place Google OAuth credentials at `~/.config/assistant/google-credentials.json` (from Google Cloud Console, Calendar API enabled). First run triggers browser auth flow.

Calendars are configured in `config.yaml` with id, name, and access (read/readwrite).

## Detect Mode

- **Query mode** — "What's on my calendar today?", "Am I free Friday?"
- **Create mode** — "Schedule a meeting with Alice tomorrow at 2pm", "Block off Friday afternoon"

## Query Mode

Read-only — never write files.

```
calendar_cli.py today                                          # today's events
calendar_cli.py events --date 2026-03-09 --days 5              # date range
calendar_cli.py events --date 2026-03 --calendar Work          # specific calendar + month
calendar_cli.py list-calendars                                 # show configured calendars
calendar_cli.py search "project review"                        # QMD search synced events
```

## Create Mode

```
calendar_cli.py create --title "Team Sync" --start 2026-03-09T14:00:00 --end 2026-03-09T15:00:00 --calendar Work
calendar_cli.py create --title "Vacation" --start 2026-03-20 --all-day --calendar Personal
```

Options: `--title`, `--start`, `--end`, `--calendar`, `--location`, `--description`, `--attendees` (comma-separated emails), `--all-day`.

Confirm with user before creating. Default duration is 1 hour if no `--end`.

## Sync

`calendar_cli.py sync --days 30` fetches events ±30 days and writes markdown files for QMD search. Run after setup or periodically.

**Never** invent event details. **Always** confirm before creating events.
