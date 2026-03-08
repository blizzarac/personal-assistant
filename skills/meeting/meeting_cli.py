#!/usr/bin/env python3
"""CLI tool for managing meeting notes with QMD-powered search."""

import argparse
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import load_config, parse_frontmatter, qmd_available, qmd_search, cmd_refresh, compact

CFG = load_config(SCRIPT_DIR)
NOTES_DIR = os.path.expanduser(CFG["data_dir"])
COLLECTION = CFG.get("collection", "meeting")

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files():
    files = {}
    if not os.path.isdir(NOTES_DIR):
        return files
    for year_dir in sorted(os.listdir(NOTES_DIR)):
        year_path = os.path.join(NOTES_DIR, year_dir)
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

    date = fm.get("date", "")
    if not date:
        m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", filename)
        if m:
            date = m.group(1)

    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", filename.replace(".md", ""))

    attendees = fm.get("attendees", fm.get("attendents", []))
    if isinstance(attendees, str):
        attendees = [attendees] if attendees else []
    clean = []
    for a in attendees:
        a = re.sub(r"\[\[([^\]]+)\]\]", r"\1", a.strip('"'))
        if a:
            clean.append(a)

    return compact({
        "Date": str(date),
        "File": rel_path,
        "Title": title,
        "Attendees": ", ".join(clean),
        "Scheduling": fm.get("scheduling", "") or "Ad hoc",
        "Description": body.strip()[:80].replace("\n", " ") if body.strip() else "",
    })


def get_all_entries():
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

def do_refresh(_args):
    cmd_refresh(discover_files)


def do_query(args):
    if args.search and qmd_available():
        qmd_results = qmd_search(COLLECTION, args.search)
        if qmd_results is not None:
            files = discover_files()
            seen, entries = set(), []
            for r in qmd_results:
                p = r.get("path", "")
                if p in files and p not in seen:
                    seen.add(p)
                    entries.append(entry_from_file(p, files[p]))
            entries = _filter(entries, args)
            print(json.dumps({"results": entries, "count": len(entries), "source": "qmd"}))
            return

    entries = get_all_entries()
    if args.search:
        t = args.search.lower()
        entries = [e for e in entries
                   if t in e.get("Title", "").lower()
                   or t in e.get("Description", "").lower()
                   or t in e.get("Attendees", "").lower()]
    entries = _filter(entries, args)
    print(json.dumps({"results": entries, "count": len(entries)}))


def _filter(entries, args):
    if args.attendee:
        q = args.attendee.lower()
        entries = [e for e in entries if q in e.get("Attendees", "").lower()]
    if args.date:
        entries = [e for e in entries if e.get("Date", "").startswith(args.date)]
    return entries


def do_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    fm, body = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "body": body}))


def main():
    p = argparse.ArgumentParser(description="Meeting CLI")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("refresh")
    q = sub.add_parser("query")
    q.add_argument("--attendee")
    q.add_argument("--date")
    q.add_argument("--search")
    r = sub.add_parser("read")
    r.add_argument("file")
    args = p.parse_args()
    cmds = {"refresh": do_refresh, "query": do_query, "read": do_read}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        p.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
