#!/usr/bin/env python3
"""CLI tool for managing the people index and queries."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from collections import defaultdict

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
            fm[current_key].append(line_stripped[2:].strip())
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

ENTRY_HEADERS = ["Name", "File", "Tags", "Birthday", "How We Met", "Last Meeting", "Family"]
BIRTHDAY_MONTHS = ["January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]

def read_index():
    if not os.path.exists(INDEX_PATH):
        return []
    rows = []
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        in_table = False
        headers = []
        for line in f:
            line = line.strip()
            if line.startswith("| Name"):
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
        "# People Index",
        f"Last updated: {today}",
        "",
        "## Entries",
        "",
        "| " + " | ".join(ENTRY_HEADERS) + " |",
        "| " + " | ".join(["------"] * len(ENTRY_HEADERS)) + " |",
    ]
    for row in sorted(entries, key=lambda r: r.get("Name", "")):
        vals = [row.get(h, "—") for h in ENTRY_HEADERS]
        lines.append("| " + " | ".join(vals) + " |")

    # Birthday calendar
    birthdays = defaultdict(list)
    for e in entries:
        bd = e.get("Birthday", "—")
        if bd and bd != "—" and len(bd) >= 10:
            try:
                month_idx = int(bd[5:7]) - 1
                day = int(bd[8:10])
                name = e.get("Name", "")
                birthdays[month_idx].append((day, name))
            except (ValueError, IndexError):
                pass

    lines.append("")
    lines.append("## Birthday Calendar")
    lines.append("")
    lines.append("| Month | People |")
    lines.append("|-------|--------|")
    for i, month_name in enumerate(BIRTHDAY_MONTHS):
        if i in birthdays:
            people = sorted(birthdays[i], key=lambda x: x[0])
            people_str = ", ".join(f"{name} ({day})" for day, name in people)
        else:
            people_str = "—"
        lines.append(f"| {month_name} | {people_str} |")

    lines.append("")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------------------------------------------------------------------------
# File parsing
# ---------------------------------------------------------------------------

def entry_from_file(filename, abs_path):
    fm = parse_frontmatter(abs_path)
    first_name = fm.get("first_name", "")
    last_name = fm.get("last_name", "")
    name = f"{first_name} {last_name}".strip() if first_name else filename.replace(".md", "")

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags] if tags else []
    tags_str = ", ".join(tags) if tags else "people"

    birthday = fm.get("birthday", "—")
    if not birthday:
        birthday = "—"

    how_we_met = fm.get("how_we_met", "—")
    if not how_we_met:
        how_we_met = "—"

    last_meeting = fm.get("last_meeting", "—")
    if not last_meeting:
        last_meeting = "—"

    # Family
    family_parts = []
    for role, key in [("father", "father"), ("mother", "mother"), ("children", "children")]:
        val = fm.get(key, "")
        if val:
            if isinstance(val, list):
                val = ", ".join(val)
            family_parts.append(f"{role}: {val}")
    family = ", ".join(family_parts) if family_parts else "—"

    # Check for duplicate filename indicator
    dup_marker = ""
    base_name = filename.replace(".md", "").strip()
    if "  " in base_name:
        dup_marker = " (duplicate?)"

    return {
        "Name": name + dup_marker,
        "File": filename,
        "Tags": tags_str,
        "Birthday": str(birthday),
        "How We Met": how_we_met,
        "Last Meeting": str(last_meeting),
        "Family": family,
    }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    all_files = {}
    for f in os.listdir(NOTES_DIR):
        if f.endswith(".md") and f not in EXCLUDE:
            all_files[f] = os.path.join(NOTES_DIR, f)

    entries = read_index()
    indexed_files = {r["File"] for r in entries}
    disk_set = set(all_files.keys())

    added = disk_set - indexed_files
    removed = indexed_files - disk_set

    if not added and not removed:
        print(json.dumps({"added": [], "removed": [], "total": len(entries)}))
        return

    if removed:
        entries = [e for e in entries if e["File"] not in removed]

    added_list = []
    for filename in sorted(added):
        try:
            entry = entry_from_file(filename, all_files[filename])
            entries.append(entry)
            added_list.append(filename)
        except Exception as e:
            sys.stderr.write(f"Error parsing {filename}: {e}\n")

    write_index(entries)
    print(json.dumps({"added": added_list, "removed": sorted(removed), "total": len(entries)}))

def cmd_search(args):
    entries = read_index()

    if args.name:
        query = args.name.lower()
        entries = [e for e in entries if query in e.get("Name", "").lower()]
    if args.tag:
        tag = args.tag.lower()
        entries = [e for e in entries if tag in e.get("Tags", "").lower()]
    if args.birthday_month:
        month = f"-{int(args.birthday_month):02d}-"
        entries = [e for e in entries if month in e.get("Birthday", "")]
    if args.how_we_met:
        query = args.how_we_met.lower()
        entries = [e for e in entries if query in e.get("How We Met", "").lower()]

    print(json.dumps({"results": entries, "count": len(entries)}))

def cmd_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        # Try adding .md
        filepath = os.path.join(NOTES_DIR, args.file + ".md")
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "content": content}))

def cmd_birthdays(args):
    entries = read_index()
    month = args.month if args.month else None

    birthdays = []
    for e in entries:
        bd = e.get("Birthday", "—")
        if bd and bd != "—" and len(bd) >= 10:
            if month:
                if bd[5:7] == f"{int(month):02d}":
                    birthdays.append({"name": e["Name"], "birthday": bd})
            else:
                birthdays.append({"name": e["Name"], "birthday": bd})

    birthdays.sort(key=lambda x: x["birthday"][5:])  # Sort by month-day
    print(json.dumps({"birthdays": birthdays, "count": len(birthdays)}))

def main():
    parser = argparse.ArgumentParser(description="Person CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Diff filesystem vs index, update index")

    s = sub.add_parser("search", help="Search people")
    s.add_argument("--name", help="Search by name (fuzzy)")
    s.add_argument("--tag", help="Filter by tag")
    s.add_argument("--birthday-month", help="People with birthdays in month (1-12)")
    s.add_argument("--how-we-met", help="Search how we met field")

    r = sub.add_parser("read", help="Read a person file")
    r.add_argument("file", help="Filename (with or without .md)")

    b = sub.add_parser("birthdays", help="List birthdays")
    b.add_argument("--month", help="Filter by month (1-12)")

    args = parser.parse_args()
    commands = {"refresh": cmd_refresh, "search": cmd_search, "read": cmd_read, "birthdays": cmd_birthdays}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
