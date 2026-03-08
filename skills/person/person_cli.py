#!/usr/bin/env python3
"""CLI tool for managing the people directory with QMD-powered search."""

import argparse
import json
import os
import re
import shutil
import subprocess
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
COLLECTION = CFG.get("collection", "person")
EXCLUDE = CFG.get("exclude", [])
if isinstance(EXCLUDE, str):
    EXCLUDE = [EXCLUDE]

# ---------------------------------------------------------------------------
# QMD helpers
# ---------------------------------------------------------------------------


def qmd_available():
    return shutil.which("qmd") is not None


def qmd_search(query_text, n=20):
    cmd = ["qmd", "query", "-c", COLLECTION, "-n", str(n), "--json", query_text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


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
# File discovery
# ---------------------------------------------------------------------------


def discover_people():
    """Find all person .md files in the data directory."""
    files = {}
    if not os.path.isdir(NOTES_DIR):
        return files
    for fname in sorted(os.listdir(NOTES_DIR)):
        if fname.endswith(".md") and fname not in EXCLUDE:
            files[fname] = os.path.join(NOTES_DIR, fname)
    return files


def entry_from_file(filename, abs_path):
    """Create an entry dict from a person file."""
    fm = parse_frontmatter(abs_path)
    first_name = fm.get("first_name", "")
    last_name = fm.get("last_name", "")
    name = f"{first_name} {last_name}".strip() if first_name else filename.replace(".md", "")

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags] if tags else []
    tags_str = ", ".join(tags) if tags else "people"

    birthday = fm.get("birthday", "")
    if not birthday:
        birthday = ""

    how_we_met = fm.get("how_we_met", "")
    if not how_we_met:
        how_we_met = ""

    last_meeting = fm.get("last_meeting", "")
    if not last_meeting:
        last_meeting = ""

    family_parts = []
    for role, key in [("father", "father"), ("mother", "mother"), ("children", "children")]:
        val = fm.get(key, "")
        if val:
            if isinstance(val, list):
                val = ", ".join(val)
            family_parts.append(f"{role}: {val}")
    family = ", ".join(family_parts) if family_parts else ""

    return {
        "Name": name,
        "File": filename,
        "Tags": tags_str,
        "Birthday": str(birthday),
        "How We Met": how_we_met,
        "Last Meeting": str(last_meeting),
        "Family": family,
    }


def get_all_entries():
    """Scan all person files and return entry dicts."""
    files = discover_people()
    entries = []
    for filename, abs_path in sorted(files.items()):
        try:
            entries.append(entry_from_file(filename, abs_path))
        except Exception as e:
            sys.stderr.write(f"Error parsing {filename}: {e}\n")
    return entries


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    """Re-embed the QMD collection."""
    if not qmd_available():
        print(json.dumps({"error": "qmd is not installed. Install with: npm install -g @tobilu/qmd"}))
        sys.exit(1)

    try:
        result = subprocess.run(["qmd", "embed"], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            total = len(discover_people())
            print(json.dumps({"status": "ok", "indexed": True, "total": total}))
        else:
            print(json.dumps({"status": "error", "message": "qmd embed failed"}))
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"status": "error", "message": "qmd embed timed out"}))
        sys.exit(1)


def cmd_search(args):
    """Search people. Uses QMD for text search, direct scan for structured filters."""
    has_text_search = args.name or args.how_we_met

    # Try QMD for text-based searches
    if has_text_search and qmd_available():
        search_term = args.name or args.how_we_met
        qmd_results = qmd_search(search_term)
        if qmd_results is not None:
            files = discover_people()
            entries = []
            seen = set()
            for result in qmd_results:
                path = result.get("path", "")
                if path in files and path not in seen:
                    seen.add(path)
                    entry = entry_from_file(path, files[path])
                    entry["_score"] = result.get("score", 0)
                    entries.append(entry)

            entries = _apply_structured_filters(entries, args)
            print(json.dumps({"results": entries, "count": len(entries), "source": "qmd"}))
            return

    # Fallback: scan all files
    entries = get_all_entries()

    # Text search fallback
    if args.name:
        query = args.name.lower()
        entries = [e for e in entries if query in e.get("Name", "").lower()]
    if args.how_we_met:
        query = args.how_we_met.lower()
        entries = [e for e in entries if query in e.get("How We Met", "").lower()]

    entries = _apply_structured_filters(entries, args)
    print(json.dumps({"results": entries, "count": len(entries), "source": "scan"}))


def _apply_structured_filters(entries, args):
    """Apply structured frontmatter filters."""
    if args.tag:
        tag = args.tag.lower()
        entries = [e for e in entries if tag in e.get("Tags", "").lower()]
    if args.birthday_month:
        month = f"-{int(args.birthday_month):02d}-"
        entries = [e for e in entries if month in e.get("Birthday", "")]
    return entries


def cmd_read(args):
    """Read a specific person file."""
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        filepath = os.path.join(NOTES_DIR, args.file + ".md")
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "content": content}))


def cmd_birthdays(args):
    """List birthdays, optionally filtered by month."""
    entries = get_all_entries()
    month = args.month if args.month else None

    birthdays = []
    for e in entries:
        bd = e.get("Birthday", "")
        if bd and len(bd) >= 10:
            if month:
                if bd[5:7] == f"{int(month):02d}":
                    birthdays.append({"name": e["Name"], "birthday": bd})
            else:
                birthdays.append({"name": e["Name"], "birthday": bd})

    birthdays.sort(key=lambda x: x["birthday"][5:])
    print(json.dumps({"birthdays": birthdays, "count": len(birthdays)}))


def main():
    parser = argparse.ArgumentParser(description="Person CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Re-embed QMD collection")

    s = sub.add_parser("search", help="Search people")
    s.add_argument("--name", help="Search by name (uses QMD when available)")
    s.add_argument("--tag", help="Filter by tag")
    s.add_argument("--birthday-month", help="People with birthdays in month (1-12)")
    s.add_argument("--how-we-met", help="Search how we met field (uses QMD when available)")

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
