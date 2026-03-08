#!/usr/bin/env python3
"""CLI tool for managing the people directory with QMD-powered search."""

import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import load_config, parse_frontmatter, qmd_available, qmd_search, cmd_refresh, compact

CFG = load_config(SCRIPT_DIR)
NOTES_DIR = os.path.expanduser(CFG["data_dir"])
COLLECTION = CFG.get("collection", "person")

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files():
    files = {}
    if not os.path.isdir(NOTES_DIR):
        return files
    for fname in sorted(os.listdir(NOTES_DIR)):
        if fname.endswith(".md"):
            files[fname] = os.path.join(NOTES_DIR, fname)
    return files


def entry_from_file(filename, abs_path):
    fm, _ = parse_frontmatter(abs_path)
    first = fm.get("first_name", "")
    last = fm.get("last_name", "")
    name = f"{first} {last}".strip() if first else filename.replace(".md", "")

    tags = fm.get("tags", [])
    if isinstance(tags, str):
        tags = [tags] if tags else []

    return compact({
        "Name": name,
        "File": filename,
        "Tags": ", ".join(tags) if tags else "people",
        "Birthday": str(fm.get("birthday", "")),
        "How We Met": fm.get("how_we_met", ""),
        "Last Meeting": str(fm.get("last_meeting", "")),
    })


def get_all_entries():
    files = discover_files()
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

def do_refresh(_args):
    cmd_refresh(discover_files)


def do_search(args):
    has_text = args.name or args.how_we_met
    if has_text and qmd_available():
        term = args.name or args.how_we_met
        qmd_results = qmd_search(COLLECTION, term)
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
    if args.name:
        q = args.name.lower()
        entries = [e for e in entries if q in e.get("Name", "").lower()]
    if args.how_we_met:
        q = args.how_we_met.lower()
        entries = [e for e in entries if q in e.get("How We Met", "").lower()]
    entries = _filter(entries, args)
    print(json.dumps({"results": entries, "count": len(entries)}))


def _filter(entries, args):
    if args.tag:
        t = args.tag.lower()
        entries = [e for e in entries if t in e.get("Tags", "").lower()]
    if args.birthday_month:
        month = f"-{int(args.birthday_month):02d}-"
        entries = [e for e in entries if month in e.get("Birthday", "")]
    return entries


def do_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        filepath = os.path.join(NOTES_DIR, args.file + ".md")
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    fm, body = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "body": body}))


def do_birthdays(args):
    entries = get_all_entries()
    month = args.month
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
    p = argparse.ArgumentParser(description="Person CLI")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("refresh")
    s = sub.add_parser("search")
    s.add_argument("--name")
    s.add_argument("--tag")
    s.add_argument("--birthday-month")
    s.add_argument("--how-we-met")
    r = sub.add_parser("read")
    r.add_argument("file")
    b = sub.add_parser("birthdays")
    b.add_argument("--month")
    args = p.parse_args()
    cmds = {"refresh": do_refresh, "search": do_search, "read": do_read, "birthdays": do_birthdays}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        p.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
