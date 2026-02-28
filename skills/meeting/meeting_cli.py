#!/usr/bin/env python3
"""CLI tool for managing the meetings index and queries."""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    cfg = {}
    with open(os.path.join(SCRIPT_DIR, "config.yaml"), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line and not line.startswith("-"):
                key, val = line.split(":", 1)
                key, val = key.strip(), val.strip()
                if val == "":
                    cfg[key] = []
                else:
                    cfg[key] = val
            elif line.startswith("- ") and cfg:
                last_key = list(cfg.keys())[-1]
                if isinstance(cfg[last_key], list):
                    cfg[last_key].append(line[2:].strip())
    return cfg

CFG = load_config()
NOTES_DIR = os.path.expanduser(CFG["data_dir"])
INDEX_PATH = os.path.join(NOTES_DIR, CFG["index_file"])
PERSON_DATA_DIR = os.path.expanduser(CFG.get("person_data_dir", "~/.local/share/assistant/person"))
EXCLUDE = CFG.get("exclude", [])
if isinstance(EXCLUDE, str):
    EXCLUDE = [EXCLUDE]

# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(filepath):
    fm = {}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    if not content.startswith("---"):
        return fm
    end = content.find("---", 3)
    if end == -1:
        return fm
    block = content[3:end]
    current_key = None
    for line in block.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if line_stripped.startswith("- ") and current_key:
            if current_key not in fm:
                fm[current_key] = []
            if not isinstance(fm[current_key], list):
                fm[current_key] = [fm[current_key]] if fm[current_key] else []
            val = line_stripped[2:].strip().strip('"')
            fm[current_key].append(val)
        elif ":" in line_stripped:
            key, val = line_stripped.split(":", 1)
            key, val = key.strip(), val.strip()
            current_key = key
            if val == "":
                fm[key] = ""
            else:
                fm[key] = val
    return fm

# ---------------------------------------------------------------------------
# Markdown table I/O
# ---------------------------------------------------------------------------

ENTRY_HEADERS = ["Date", "File", "Title", "Attendees", "Scheduling", "Description"]

def read_index():
    if not os.path.exists(INDEX_PATH):
        return []
    rows = []
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        in_table = False
        headers = []
        for line in f:
            line = line.strip()
            if line.startswith("| Date"):
                headers = [h.strip() for h in line.strip("|").split("|")]
                in_table = True
                continue
            if in_table and line.startswith("|---"):
                continue
            if in_table and line.startswith("|"):
                vals = [v.strip() for v in line.strip("|").split("|")]
                row = {}
                for i, h in enumerate(headers):
                    row[h] = vals[i] if i < len(vals) else ""
                rows.append(row)
            elif in_table and not line.startswith("|"):
                break
    return rows

def write_index(entries):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Meetings Index",
        f"Last updated: {today}",
        "",
        "## Entries",
        "",
        "| " + " | ".join(ENTRY_HEADERS) + " |",
        "| " + " | ".join(["------"] * len(ENTRY_HEADERS)) + " |",
    ]
    for row in sorted(entries, key=lambda r: r.get("Date", "")):
        vals = [row.get(h, "") for h in ENTRY_HEADERS]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_meetings():
    """Find all meeting .md files in year/ subfolders."""
    files = {}
    if not os.path.isdir(NOTES_DIR):
        return files
    for year_dir in sorted(os.listdir(NOTES_DIR)):
        year_path = os.path.join(NOTES_DIR, year_dir)
        if not os.path.isdir(year_path) or not re.match(r"^\d{4}$", year_dir):
            continue
        for fname in os.listdir(year_path):
            if fname.endswith(".md") and fname not in EXCLUDE:
                rel_path = f"{year_dir}/{fname}"
                files[rel_path] = os.path.join(year_path, fname)
    return files

def entry_from_file(rel_path, abs_path):
    fm = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)

    date = fm.get("date", "")
    if not date:
        # Try to extract from filename: Title (YYYY-MM-DD).md
        m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", filename)
        if m:
            date = m.group(1)

    # Title from filename
    title = filename.replace(".md", "")
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", title)

    # Attendees
    attendees = fm.get("attendees", fm.get("attendents", []))
    if isinstance(attendees, str):
        attendees = [attendees] if attendees else []
    # Clean wiki-link formatting for the index
    clean_attendees = []
    for a in attendees:
        a = a.strip('"')
        a = re.sub(r"\[\[([^\]]+)\]\]", r"\1", a)
        if a:
            clean_attendees.append(a)
    attendees_str = ", ".join(clean_attendees)

    scheduling = fm.get("scheduling", "Ad hoc")
    if not scheduling:
        scheduling = "Ad hoc"

    # Description: first 80 chars of body content
    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
    # Skip frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:].strip()
        else:
            body = ""
    else:
        body = content.strip()
    description = body[:80].replace("\n", " ").replace("|", "/") if body else ""

    return {
        "Date": str(date),
        "File": rel_path,
        "Title": title,
        "Attendees": attendees_str,
        "Scheduling": scheduling,
        "Description": description,
    }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    disk_files = discover_meetings()
    entries = read_index()
    indexed_files = {r["File"] for r in entries}
    disk_set = set(disk_files.keys())

    added = disk_set - indexed_files
    removed = indexed_files - disk_set

    if not added and not removed:
        print(json.dumps({"added": [], "removed": [], "total": len(entries)}))
        return

    if removed:
        entries = [e for e in entries if e["File"] not in removed]

    added_list = []
    for rel_path in sorted(added):
        try:
            entry = entry_from_file(rel_path, disk_files[rel_path])
            entries.append(entry)
            added_list.append(rel_path)
        except Exception as e:
            sys.stderr.write(f"Error parsing {rel_path}: {e}\n")

    write_index(entries)
    print(json.dumps({"added": added_list, "removed": sorted(removed), "total": len(entries)}))

def cmd_query(args):
    entries = read_index()

    if args.attendee:
        query = args.attendee.lower()
        entries = [e for e in entries if query in e.get("Attendees", "").lower()]
    if args.date:
        query = args.date
        entries = [e for e in entries if e.get("Date", "").startswith(query)]
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries
                   if term in e.get("Title", "").lower()
                   or term in e.get("Description", "").lower()
                   or term in e.get("Attendees", "").lower()]

    print(json.dumps({"results": entries, "count": len(entries)}))

def cmd_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "content": content}))

def main():
    parser = argparse.ArgumentParser(description="Meeting CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Diff filesystem vs index, update index")

    q = sub.add_parser("query", help="Query meetings")
    q.add_argument("--attendee", help="Filter by attendee name")
    q.add_argument("--date", help="Filter by date prefix (YYYY, YYYY-MM, YYYY-MM-DD)")
    q.add_argument("--search", help="Search titles and descriptions")

    r = sub.add_parser("read", help="Read a meeting file")
    r.add_argument("file", help="Relative file path")

    args = parser.parse_args()
    commands = {"refresh": cmd_refresh, "query": cmd_query, "read": cmd_read}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
