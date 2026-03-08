#!/usr/bin/env python3
"""CLI tool for managing journal entries with QMD-powered search."""

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
COLLECTION = CFG.get("collection", "journal")
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
# File discovery
# ---------------------------------------------------------------------------


def discover_files():
    """Find all journal .md files in year subfolders."""
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
    """Create an entry dict from a journal file."""
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

    description = fm.get("description", "")
    if not description:
        description = ""

    return {
        "Date": date_str,
        "File": rel_path,
        "Type": entry_type,
        "Description": description,
    }


def get_all_entries():
    """Scan all journal files and return entry dicts."""
    files = discover_files()
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
            total = len(discover_files())
            print(json.dumps({"status": "ok", "indexed": True, "total": total}))
        else:
            print(json.dumps({"status": "error", "message": "qmd embed failed"}))
            sys.exit(1)
    except subprocess.TimeoutExpired:
        print(json.dumps({"status": "error", "message": "qmd embed timed out"}))
        sys.exit(1)


def cmd_query(args):
    """Query journal entries. Uses QMD for text search, direct scan for structured filters."""
    # Text search via QMD
    if args.search and qmd_available():
        qmd_results = qmd_search(args.search)
        if qmd_results is not None:
            files = discover_files()
            entries = []
            seen = set()
            for result in qmd_results:
                path = result.get("path", "")
                if path in files and path not in seen:
                    seen.add(path)
                    entry = entry_from_file(path, files[path])
                    entry["_score"] = result.get("score", 0)
                    entries.append(entry)

            # Apply structured filters on top
            entries = _apply_structured_filters(entries, args)
            print(json.dumps({"results": entries, "count": len(entries), "source": "qmd"}))
            return

    # Fallback: scan all files
    entries = get_all_entries()

    # Text search fallback
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries if term in e.get("Description", "").lower()]

    entries = _apply_structured_filters(entries, args)
    source = "scan-fallback" if args.search else "scan"
    print(json.dumps({"results": entries, "count": len(entries), "source": source}))


def _apply_structured_filters(entries, args):
    """Apply structured frontmatter filters."""
    if args.date:
        query = args.date
        entries = [e for e in entries if e.get("Date", "").startswith(query)]
    if args.tag:
        tag = args.tag.lower()
        entries = [e for e in entries if tag in e.get("Type", "").lower()]
    return entries


def cmd_read(args):
    """Read a specific journal file."""
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

    sub.add_parser("refresh", help="Re-embed QMD collection")

    q = sub.add_parser("query", help="Query journal entries")
    q.add_argument("--date", help="Filter by date prefix (YYYY, YYYY-MM, YYYY-MM-DD)")
    q.add_argument("--tag", help="Filter by type (work/personal)")
    q.add_argument("--search", help="Search descriptions (uses QMD when available)")

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
