#!/usr/bin/env python3
"""CLI tool for Google Calendar integration with QMD-powered search."""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import parse_frontmatter, qmd_available, qmd_search, qmd_embed, compact


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_calendar_config():
    """Parse config.yaml including nested calendar list entries."""
    cfg = {}
    calendars = []
    current_cal = None
    with open(os.path.join(SCRIPT_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        for line in f:
            raw = line.rstrip("\n")
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Detect list item under calendars
            if raw.startswith("- ") and current_cal is not None:
                # New calendar entry
                if current_cal:
                    calendars.append(current_cal)
                current_cal = {}
                # Parse key on same line as dash: "- id: primary"
                rest = raw[2:].strip()
                if ":" in rest:
                    k, v = rest.split(":", 1)
                    current_cal[k.strip()] = v.strip()
            elif raw.startswith("  ") and current_cal is not None and ":" in stripped:
                # Continuation of current calendar entry
                k, v = stripped.split(":", 1)
                current_cal[k.strip()] = v.strip()
            elif ":" in stripped and not stripped.startswith("-"):
                key, val = stripped.split(":", 1)
                key, val = key.strip(), val.strip()
                if key == "calendars":
                    current_cal = {}  # start collecting calendar entries
                else:
                    cfg[key] = val
    if current_cal:
        calendars.append(current_cal)
    # Remove empty dicts from parsing
    cfg["calendars"] = [c for c in calendars if c.get("id")]
    return cfg


CFG = load_calendar_config()
DATA_DIR = os.path.expanduser(CFG.get("data_dir", "~/.local/share/assistant/calendar"))
COLLECTION = CFG.get("collection", "calendar")
CREDENTIALS_FILE = os.path.expanduser(CFG.get("credentials_file", "~/.config/assistant/google-credentials.json"))
TOKEN_FILE = os.path.expanduser(CFG.get("token_file", "~/.config/assistant/google-token.json"))
CALENDARS = CFG.get("calendars", [{"id": "primary", "name": "Personal", "access": "readwrite"}])

SCOPES = ["https://www.googleapis.com/auth/calendar"]


# ---------------------------------------------------------------------------
# Google Calendar API auth
# ---------------------------------------------------------------------------

def get_calendar_service():
    """Authenticate and return a Google Calendar API service object."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print(json.dumps({"error": "Missing dependencies. Install with: pip install google-api-python-client google-auth-oauthlib"}))
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(json.dumps({"error": f"Credentials file not found: {CREDENTIALS_FILE}",
                                  "help": "Download OAuth client credentials from Google Cloud Console and save to this path."}))
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_calendar_config(name_or_id):
    """Find a calendar config entry by name or id (case-insensitive name match)."""
    for cal in CALENDARS:
        if cal["id"] == name_or_id:
            return cal
        if cal.get("name", "").lower() == name_or_id.lower():
            return cal
    return None


def writable_calendars():
    """Return calendar configs with readwrite access."""
    return [c for c in CALENDARS if c.get("access") == "readwrite"]


# ---------------------------------------------------------------------------
# Event markdown files (for QMD search)
# ---------------------------------------------------------------------------

def event_to_markdown(event, calendar_name):
    """Convert a Google Calendar event dict to markdown content."""
    start = event.get("start", {})
    end = event.get("end", {})
    start_dt = start.get("dateTime", start.get("date", ""))
    end_dt = end.get("dateTime", end.get("date", ""))
    summary = event.get("summary", "Untitled")
    description = event.get("description", "")
    location = event.get("location", "")
    attendees = event.get("attendees", [])
    status = event.get("status", "confirmed")

    att_list = []
    for a in attendees:
        name = a.get("displayName", a.get("email", ""))
        if name:
            att_list.append(name)

    lines = ["---"]
    lines.append("tags: [calendar]")
    lines.append(f"date: {start_dt}")
    lines.append(f"end_date: {end_dt}")
    lines.append(f"calendar: {calendar_name}")
    lines.append(f"status: {status}")
    lines.append(f"event_id: {event.get('id', '')}")
    if location:
        lines.append(f"location: {location}")
    if att_list:
        lines.append("attendees:")
        for a in att_list:
            lines.append(f'  - "{a}"')
    lines.append("---")
    lines.append("")
    if description:
        lines.append(description.strip())

    return "\n".join(lines), summary


def event_filename(event):
    """Generate a filename for a calendar event."""
    start = event.get("start", {})
    start_str = start.get("dateTime", start.get("date", ""))
    date = start_str[:10] if start_str else "unknown"
    summary = event.get("summary", "Untitled")
    # Sanitize filename
    safe_title = re.sub(r'[^\w\s\-]', '', summary).strip()[:60]
    return f"{safe_title} ({date}).md"


def sync_events_to_files(events, calendar_name, year):
    """Write event markdown files to data dir. Returns count of files written."""
    year_dir = os.path.join(DATA_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)
    count = 0
    for event in events:
        content, _title = event_to_markdown(event, calendar_name)
        fname = event_filename(event)
        filepath = os.path.join(year_dir, fname)
        # Only write if changed
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                if f.read() == content:
                    continue
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        count += 1
    return count


# ---------------------------------------------------------------------------
# File discovery (for QMD and local queries)
# ---------------------------------------------------------------------------

def discover_files():
    files = {}
    if not os.path.isdir(DATA_DIR):
        return files
    for year_dir in sorted(os.listdir(DATA_DIR)):
        year_path = os.path.join(DATA_DIR, year_dir)
        if not os.path.isdir(year_path) or not re.match(r"^\d{4}$", year_dir):
            continue
        for fname in os.listdir(year_path):
            if fname.endswith(".md"):
                rel_path = f"{year_dir}/{fname}"
                files[rel_path] = os.path.join(year_path, fname)
    return files


def entry_from_file(rel_path, abs_path):
    fm, body = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", filename.replace(".md", ""))
    return compact({
        "Date": fm.get("date", ""),
        "End": fm.get("end_date", ""),
        "File": rel_path,
        "Title": title,
        "Calendar": fm.get("calendar", ""),
        "Location": fm.get("location", ""),
        "Status": fm.get("status", ""),
    })


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def do_list_calendars(_args):
    """List configured calendars."""
    result = []
    for cal in CALENDARS:
        result.append({"id": cal["id"], "name": cal.get("name", cal["id"]), "access": cal.get("access", "read")})
    print(json.dumps({"calendars": result}))


def do_today(args):
    """Show today's events from all configured calendars."""
    do_events(args, days=1)


def do_events(args, days=None):
    """Fetch events from Google Calendar API."""
    service = get_calendar_service()

    # Date range
    if getattr(args, "date", None):
        # Parse YYYY-MM-DD or YYYY-MM
        if len(args.date) == 7:  # YYYY-MM
            start = datetime.strptime(args.date + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1)
            else:
                end = start.replace(month=start.month + 1)
        else:
            start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = start + timedelta(days=int(getattr(args, "days", None) or days or 1))
    else:
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=int(getattr(args, "days", None) or days or 7))

    time_min = start.isoformat()
    time_max = end.isoformat()

    # Filter to specific calendar if requested
    cals = CALENDARS
    if getattr(args, "calendar", None):
        cal_cfg = get_calendar_config(args.calendar)
        if not cal_cfg:
            print(json.dumps({"error": f"Unknown calendar: {args.calendar}", "configured": [c.get("name", c["id"]) for c in CALENDARS]}))
            return
        cals = [cal_cfg]

    all_events = []
    for cal in cals:
        try:
            result = service.events().list(
                calendarId=cal["id"],
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=100,
            ).execute()
            events = result.get("items", [])
            for e in events:
                e["_calendar_name"] = cal.get("name", cal["id"])
            all_events.extend(events)
        except Exception as e:
            sys.stderr.write(f"Error fetching {cal.get('name', cal['id'])}: {e}\n")

    # Sort by start time
    def sort_key(e):
        s = e.get("start", {})
        return s.get("dateTime", s.get("date", ""))
    all_events.sort(key=sort_key)

    entries = []
    for e in all_events:
        start_info = e.get("start", {})
        end_info = e.get("end", {})
        start_dt = start_info.get("dateTime", start_info.get("date", ""))
        end_dt = end_info.get("dateTime", end_info.get("date", ""))

        attendees = []
        for a in e.get("attendees", []):
            name = a.get("displayName", a.get("email", ""))
            if name:
                attendees.append(name)

        entries.append(compact({
            "Summary": e.get("summary", "Untitled"),
            "Start": start_dt,
            "End": end_dt,
            "Calendar": e.get("_calendar_name", ""),
            "Location": e.get("location", ""),
            "Attendees": ", ".join(attendees),
            "Status": e.get("status", ""),
            "EventId": e.get("id", ""),
        }))

    print(json.dumps({"results": entries, "count": len(entries), "range": {"from": time_min, "to": time_max}}))


def do_create(args):
    """Create a new calendar event."""
    # Find target calendar
    cal_name = getattr(args, "calendar", None) or "primary"
    cal_cfg = get_calendar_config(cal_name)
    if not cal_cfg:
        print(json.dumps({"error": f"Unknown calendar: {cal_name}", "configured": [c.get("name", c["id"]) for c in CALENDARS]}))
        return
    if cal_cfg.get("access") != "readwrite":
        print(json.dumps({"error": f"Calendar '{cal_cfg.get('name', cal_cfg['id'])}' is read-only"}))
        return

    service = get_calendar_service()

    event_body = {"summary": args.title}

    # Handle all-day vs timed events
    if getattr(args, "all_day", False):
        event_body["start"] = {"date": args.start}
        if args.end:
            event_body["end"] = {"date": args.end}
        else:
            # All-day events: end is exclusive, so next day
            end_date = datetime.strptime(args.start, "%Y-%m-%d") + timedelta(days=1)
            event_body["end"] = {"date": end_date.strftime("%Y-%m-%d")}
    else:
        event_body["start"] = {"dateTime": args.start}
        if args.end:
            event_body["end"] = {"dateTime": args.end}
        else:
            # Default 1 hour
            try:
                start_dt = datetime.fromisoformat(args.start)
                end_dt = start_dt + timedelta(hours=1)
                event_body["end"] = {"dateTime": end_dt.isoformat()}
            except ValueError:
                event_body["end"] = {"dateTime": args.start}

    if getattr(args, "location", None):
        event_body["location"] = args.location
    if getattr(args, "description", None):
        event_body["description"] = args.description
    if getattr(args, "attendees", None):
        event_body["attendees"] = [{"email": email.strip()} for email in args.attendees.split(",")]

    try:
        created = service.events().insert(calendarId=cal_cfg["id"], body=event_body).execute()
        print(json.dumps(compact({
            "status": "created",
            "event_id": created.get("id", ""),
            "summary": created.get("summary", ""),
            "start": created.get("start", {}).get("dateTime", created.get("start", {}).get("date", "")),
            "calendar": cal_cfg.get("name", cal_cfg["id"]),
            "link": created.get("htmlLink", ""),
        })))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


def do_sync(args):
    """Sync events from Google Calendar to local markdown files for QMD search."""
    service = get_calendar_service()

    days = int(getattr(args, "days", None) or 30)
    start = datetime.now(timezone.utc) - timedelta(days=days)
    end = datetime.now(timezone.utc) + timedelta(days=days)

    cals = CALENDARS
    if getattr(args, "calendar", None):
        cal_cfg = get_calendar_config(args.calendar)
        if not cal_cfg:
            print(json.dumps({"error": f"Unknown calendar: {args.calendar}"}))
            return
        cals = [cal_cfg]

    total_synced = 0
    for cal in cals:
        try:
            result = service.events().list(
                calendarId=cal["id"],
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=500,
            ).execute()
            events = result.get("items", [])
            cal_name = cal.get("name", cal["id"])

            for e in events:
                s = e.get("start", {})
                date_str = s.get("dateTime", s.get("date", ""))
                if date_str:
                    year = int(date_str[:4])
                    total_synced += sync_events_to_files([e], cal_name, year)
        except Exception as e:
            sys.stderr.write(f"Error syncing {cal.get('name', cal['id'])}: {e}\n")

    # Embed after sync
    if qmd_available():
        qmd_embed()

    print(json.dumps({"status": "ok", "synced": total_synced, "total_files": len(discover_files())}))


def do_search(args):
    """Search synced calendar events via QMD or local file scan."""
    if qmd_available():
        qmd_results = qmd_search(COLLECTION, args.query)
        if qmd_results is not None:
            files = discover_files()
            entries = []
            seen = set()
            for r in qmd_results:
                p = r.get("path", "")
                if p in files and p not in seen:
                    seen.add(p)
                    entries.append(entry_from_file(p, files[p]))
            if getattr(args, "calendar", None):
                entries = [e for e in entries if e.get("Calendar", "").lower() == args.calendar.lower()]
            print(json.dumps({"results": entries, "count": len(entries), "source": "qmd"}))
            return

    # Fallback: local file scan
    files = discover_files()
    query = args.query.lower()
    entries = []
    for rel_path, abs_path in sorted(files.items()):
        try:
            entry = entry_from_file(rel_path, abs_path)
            if query in entry.get("Title", "").lower() or query in rel_path.lower():
                entries.append(entry)
        except Exception:
            pass
    print(json.dumps({"results": entries, "count": len(entries)}))


def do_read(args):
    """Read a synced calendar event file."""
    filepath = os.path.join(DATA_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    fm, body = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "body": body}))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Google Calendar CLI")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("list-calendars", help="List configured calendars")
    sub.add_parser("today", help="Show today's events")

    ev = sub.add_parser("events", help="Fetch events for a date range")
    ev.add_argument("--date", help="Start date: YYYY-MM-DD or YYYY-MM")
    ev.add_argument("--days", type=int, default=7, help="Number of days (default: 7)")
    ev.add_argument("--calendar", help="Calendar name or ID")

    cr = sub.add_parser("create", help="Create a new event")
    cr.add_argument("--title", required=True, help="Event title")
    cr.add_argument("--start", required=True, help="Start: YYYY-MM-DD (all-day) or ISO datetime")
    cr.add_argument("--end", help="End: YYYY-MM-DD or ISO datetime")
    cr.add_argument("--calendar", help="Target calendar name or ID")
    cr.add_argument("--location", help="Event location")
    cr.add_argument("--description", help="Event description")
    cr.add_argument("--attendees", help="Comma-separated email addresses")
    cr.add_argument("--all-day", action="store_true", help="Create all-day event")

    sy = sub.add_parser("sync", help="Sync events to local markdown for QMD search")
    sy.add_argument("--days", type=int, default=30, help="Days past and future to sync (default: 30)")
    sy.add_argument("--calendar", help="Calendar name or ID")

    se = sub.add_parser("search", help="Search synced events via QMD")
    se.add_argument("query", help="Search query")
    se.add_argument("--calendar", help="Filter by calendar name")

    rd = sub.add_parser("read", help="Read a synced event file")
    rd.add_argument("file", help="Relative path to event file")

    args = p.parse_args()
    cmds = {
        "list-calendars": do_list_calendars,
        "today": do_today,
        "events": do_events,
        "create": do_create,
        "sync": do_sync,
        "search": do_search,
        "read": do_read,
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
