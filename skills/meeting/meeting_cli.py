#!/usr/bin/env python3
"""CLI tool for managing meeting notes with QMD-powered search."""

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
COLLECTION = CFG.get("collection", "meeting")
PERSON_DATA_DIR = os.path.expanduser(CFG.get("person_data_dir", "~/.local/share/assistant/person"))
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
    """Create an entry dict from a meeting file."""
    fm = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)

    date = fm.get("date", "")
    if not date:
        m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", filename)
        if m:
            date = m.group(1)

    title = filename.replace(".md", "")
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", title)

    attendees = fm.get("attendees", fm.get("attendents", []))
    if isinstance(attendees, str):
        attendees = [attendees] if attendees else []
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

    with open(abs_path, "r", encoding="utf-8") as f:
        content = f.read()
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


def get_all_entries():
    """Scan all meeting files and return entry dicts."""
    files = discover_meetings()
    entries = []
    for rel_path, abs_path in sorted(files.items()):
        try:
            entries.append(entry_from_file(rel_path, abs_path))
        except Exception as e:
            sys.stderr.write(f"Error parsing {rel_path}: {e}\n")
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
            total = len(discover_meetings())
            print(json.dumps({"status": "ok", "indexed": True, "total": total}))
        else:
            print(json.dumps({"status": "error", "message": "qmd embed failed"}))
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"status": "error", "message": "qmd embed timed out"}))
        sys.exit(1)


def cmd_query(args):
    """Query meetings. Uses QMD for text search, direct scan for structured filters."""
    # Text search via QMD
    if args.search and qmd_available():
        qmd_results = qmd_search(args.search)
        if qmd_results is not None:
            files = discover_meetings()
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
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries
                   if term in e.get("Title", "").lower()
                   or term in e.get("Description", "").lower()
                   or term in e.get("Attendees", "").lower()]

    entries = _apply_structured_filters(entries, args)
    source = "scan-fallback" if args.search else "scan"
    print(json.dumps({"results": entries, "count": len(entries), "source": source}))


def _apply_structured_filters(entries, args):
    """Apply structured frontmatter filters."""
    if args.attendee:
        query = args.attendee.lower()
        entries = [e for e in entries if query in e.get("Attendees", "").lower()]
    if args.date:
        query = args.date
        entries = [e for e in entries if e.get("Date", "").startswith(query)]
    return entries


def cmd_read(args):
    """Read a specific meeting file."""
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

    sub.add_parser("refresh", help="Re-embed QMD collection")

    q = sub.add_parser("query", help="Query meetings")
    q.add_argument("--attendee", help="Filter by attendee name")
    q.add_argument("--date", help="Filter by date prefix (YYYY, YYYY-MM, YYYY-MM-DD)")
    q.add_argument("--search", help="Search titles and descriptions (uses QMD when available)")

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
