#!/usr/bin/env python3
"""CLI tool for managing journal entries with QMD-powered search."""

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
COLLECTION = CFG.get("collection", "journal")

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
    fm, _ = parse_frontmatter(abs_path)
    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]
    return compact({
        "Date": str(fm.get("date", "")),
        "File": rel_path,
        "Type": "work" if "work" in tags else "personal",
        "Description": fm.get("description", ""),
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
        entries = [e for e in entries if t in e.get("Description", "").lower()]
    entries = _filter(entries, args)
    print(json.dumps({"results": entries, "count": len(entries)}))


def _filter(entries, args):
    if args.date:
        entries = [e for e in entries if e.get("Date", "").startswith(args.date)]
    if args.tag:
        t = args.tag.lower()
        entries = [e for e in entries if t in e.get("Type", "").lower()]
    return entries


def do_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        for year_dir in os.listdir(NOTES_DIR):
            candidate = os.path.join(NOTES_DIR, year_dir, args.file)
            if os.path.exists(candidate):
                filepath = candidate
                break
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    fm, body = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "body": body}))


def main():
    p = argparse.ArgumentParser(description="Journal CLI")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("refresh")
    q = sub.add_parser("query")
    q.add_argument("--date")
    q.add_argument("--tag")
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
