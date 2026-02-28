#!/usr/bin/env python3
"""CLI tool for managing the journal index and queries."""

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
EXCLUDE = CFG.get("exclude", [])
if isinstance(EXCLUDE, str):
    EXCLUDE = [EXCLUDE]

# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file."""
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
                fm[current_key] = []
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

ENTRY_HEADERS = ["Date", "File", "Type", "Description"]

def read_index_table(filepath, start_marker):
    """Read a markdown table section into list of dicts."""
    if not os.path.exists(filepath):
        return []
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        in_section = False
        in_table = False
        headers = []
        for line in f:
            line = line.strip()
            if line.startswith(start_marker):
                in_section = True
                continue
            if in_section and line.startswith("| ") and not in_table:
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
    """Write the full journal index file."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Journal Index",
        f"Last updated: {today}",
        "",
        "## Entries",
        "",
        "| " + " | ".join(ENTRY_HEADERS) + " |",
        "| " + " | ".join(["------"] * len(ENTRY_HEADERS)) + " |",
    ]
    for row in sorted(entries, key=lambda r: r.get("Date", "")):
        vals = [row.get(h, "—") for h in ENTRY_HEADERS]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files():
    """Find all journal .md files in year subfolders."""
    files = {}
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
    """Create an index entry from a journal file."""
    fm = parse_frontmatter(abs_path)
    date = fm.get("date", "")
    if isinstance(date, str):
        date_str = date
    else:
        date_str = str(date)

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    entry_type = "work" if "work" in tags else "personal"

    description = fm.get("description", "—")
    if not description:
        description = "—"

    return {
        "Date": date_str,
        "File": rel_path,
        "Type": entry_type,
        "Description": description,
    }

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    disk_files = discover_files()
    entries = read_index_table(INDEX_PATH, "## Entries")
    indexed_files = {r["File"] for r in entries}
    disk_set = set(disk_files.keys())

    added_files = disk_set - indexed_files
    removed_files = indexed_files - disk_set

    if not added_files and not removed_files:
        print(json.dumps({"added": [], "removed": [], "total": len(entries)}))
        return

    if removed_files:
        entries = [e for e in entries if e["File"] not in removed_files]

    added_list = []
    for rel_path in sorted(added_files):
        try:
            entry = entry_from_file(rel_path, disk_files[rel_path])
            entries.append(entry)
            added_list.append(rel_path)
        except Exception as e:
            sys.stderr.write(f"Error parsing {rel_path}: {e}\n")

    write_index(entries)
    print(json.dumps({"added": added_list, "removed": sorted(removed_files), "total": len(entries)}))

def cmd_query(args):
    entries = read_index_table(INDEX_PATH, "## Entries")

    if args.date:
        query = args.date
        entries = [e for e in entries if e.get("Date", "").startswith(query)]
    if args.tag:
        tag = args.tag.lower()
        entries = [e for e in entries if tag in e.get("Type", "").lower()]
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries if term in e.get("Description", "").lower()]

    print(json.dumps({"results": entries, "count": len(entries)}))

def cmd_read(args):
    # Try as relative path first, then as filename in any year dir
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        # Search year dirs
        for year_dir in os.listdir(NOTES_DIR):
            candidate = os.path.join(NOTES_DIR, year_dir, args.file)
            if os.path.exists(candidate):
                filepath = candidate
                break
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "content": content}))

def main():
    parser = argparse.ArgumentParser(description="Journal CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Diff filesystem vs index, update index")

    q = sub.add_parser("query", help="Query journal entries")
    q.add_argument("--date", help="Filter by date prefix (YYYY, YYYY-MM, YYYY-MM-DD)")
    q.add_argument("--tag", help="Filter by type (work/personal)")
    q.add_argument("--search", help="Search descriptions")

    r = sub.add_parser("read", help="Read a journal file")
    r.add_argument("file", help="Filename or relative path")

    args = parser.parse_args()
    commands = {"refresh": cmd_refresh, "query": cmd_query, "read": cmd_read}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
