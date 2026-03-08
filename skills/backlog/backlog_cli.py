#!/usr/bin/env python3
"""CLI tool for managing tasks with QMD-powered search."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
from common import load_config, parse_frontmatter, qmd_available, qmd_search, qmd_embed, compact

CFG = load_config(SCRIPT_DIR)
NOTES_DIR = os.path.expanduser(CFG["data_dir"])
UNASSIGNED_DIR = CFG.get("unassigned_dir", "_unassigned")
COLLECTION = CFG.get("collection", "backlog")

# ---------------------------------------------------------------------------
# Frontmatter writing (backlog-specific — create/update/close need this)
# ---------------------------------------------------------------------------

FRONTMATTER_FIELD_ORDER = [
    "links", "tags", "status", "inform", "outcome", "project",
    "priority", "due_date", "created_date", "completed_date", "description",
]


def _write_fm_field(lines, key, value):
    if isinstance(value, list):
        lines.append(f"{key}:")
        for item in value:
            lines.append(f"  - {item}")
    elif value == "" or value is None:
        lines.append(f"{key}:")
    else:
        lines.append(f"{key}: {value}")


def write_frontmatter(filepath, fm, body=""):
    lines = ["---"]
    written = set()
    for key in FRONTMATTER_FIELD_ORDER:
        if key in fm:
            _write_fm_field(lines, key, fm[key])
            written.add(key)
    for key in fm:
        if key not in written:
            _write_fm_field(lines, key, fm[key])
    lines.append("---")
    lines.append(body if body else "")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def update_frontmatter_in_file(filepath, updates):
    fm, body = parse_frontmatter(filepath)
    fm.update(updates)
    write_frontmatter(filepath, fm, body)

# ---------------------------------------------------------------------------
# QMD collection management (backlog-specific)
# ---------------------------------------------------------------------------

def qmd_ensure_collection():
    try:
        result = subprocess.run(
            ["qmd", "collection", "list"], capture_output=True, text=True, timeout=10
        )
        if COLLECTION in result.stdout:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    try:
        result = subprocess.run(
            ["qmd", "collection", "add", NOTES_DIR, "--name", COLLECTION],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            subprocess.run(
                ["qmd", "context", "add", f"qmd://{COLLECTION}",
                 "Task backlog with project-based organization. Each task has YAML frontmatter with status, priority, due_date, and project fields."],
                capture_output=True, text=True, timeout=10,
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def discover_files():
    files = {}
    if not os.path.isdir(NOTES_DIR):
        return files
    for project_dir in sorted(os.listdir(NOTES_DIR)):
        if project_dir.startswith("."):
            continue
        project_path = os.path.join(NOTES_DIR, project_dir)
        if not os.path.isdir(project_path):
            continue
        for item in sorted(os.listdir(project_path)):
            if item.startswith("."):
                continue
            item_path = os.path.join(project_path, item)
            if os.path.isfile(item_path) and item.endswith(".md"):
                files[f"{project_dir}/{item}"] = item_path
            elif os.path.isdir(item_path):
                inner_md = os.path.join(item_path, item + ".md")
                if os.path.isfile(inner_md):
                    files[f"{project_dir}/{item}/{item}.md"] = inner_md
    return files


def entry_from_file(rel_path, abs_path):
    fm, body = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)
    title = filename.replace(".md", "")

    project = fm.get("project", "")
    if not project:
        project = rel_path.split("/")[0] if "/" in rel_path else ""

    status = fm.get("status", "")
    if not status:
        completed = fm.get("completed", "")
        if isinstance(completed, str):
            completed = completed.lower().strip()
        status = "done" if completed == "true" else "open"

    priority = fm.get("priority", fm.get("Priority", ""))
    description = fm.get("description", "") or fm.get("outcome", "")
    if not description:
        b = body.strip() if body else ""
        description = b[:80].replace("\n", " ") if b else ""

    return compact({
        "Title": title,
        "File": rel_path,
        "Project": str(project),
        "Status": str(status),
        "Priority": str(priority),
        "Due Date": str(fm.get("due_date", fm.get("due", ""))),
        "Created": str(fm.get("created_date", fm.get("created", ""))),
        "Completed": str(fm.get("completed_date", "")),
        "Description": str(description),
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
    if not qmd_available():
        print(json.dumps({"error": "qmd not installed"}))
        sys.exit(1)
    qmd_ensure_collection()
    if qmd_embed():
        print(json.dumps({"status": "ok", "total": len(discover_files())}))
    else:
        print(json.dumps({"status": "error", "message": "qmd embed failed"}))
        sys.exit(1)


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
        entries = [e for e in entries if t in e.get("Title", "").lower() or t in e.get("Description", "").lower()]
    entries = _filter(entries, args)
    print(json.dumps({"results": entries, "count": len(entries)}))


def _filter(entries, args):
    if args.status:
        s = args.status.lower()
        entries = [e for e in entries if e.get("Status", "").lower() == s]
    if args.project:
        p = args.project.lower()
        entries = [e for e in entries if p in e.get("Project", "").lower()]
    if args.priority:
        entries = [e for e in entries if e.get("Priority", "") == args.priority]
    if args.due_before:
        entries = [e for e in entries if e.get("Due Date", "") and e["Due Date"] < args.due_before]
    if args.due_after:
        entries = [e for e in entries if e.get("Due Date", "") and e["Due Date"] > args.due_after]
    return entries


def do_read(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        for project_dir in os.listdir(NOTES_DIR):
            project_path = os.path.join(NOTES_DIR, project_dir)
            if not os.path.isdir(project_path) or project_dir.startswith("."):
                continue
            candidate = os.path.join(project_path, args.file)
            if os.path.exists(candidate):
                filepath = candidate
                break
            name_no_ext = args.file.replace(".md", "") if args.file.endswith(".md") else args.file
            candidate2 = os.path.join(project_path, name_no_ext, args.file)
            if os.path.exists(candidate2):
                filepath = candidate2
                break
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    fm, body = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "body": body}))


def do_stats(args):
    entries = get_all_entries()
    if args.project:
        p = args.project.lower()
        entries = [e for e in entries if p in e.get("Project", "").lower()]
    stats = _compute_stats(entries)
    print(json.dumps({"total_entries": len(entries), "project_stats": stats}))


def _compute_stats(entries):
    projects = defaultdict(lambda: {"open": 0, "in_progress": 0, "blocked": 0, "done": 0, "total": 0})
    for e in entries:
        proj = e.get("Project", "") or "_unassigned"
        status = e.get("Status", "open").lower().strip()
        projects[proj]["total"] += 1
        if status in ("done", "completed", "closed"):
            projects[proj]["done"] += 1
        elif status in ("in progress", "in_progress", "in-progress", "wip"):
            projects[proj]["in_progress"] += 1
        elif status in ("blocked", "waiting"):
            projects[proj]["blocked"] += 1
        else:
            projects[proj]["open"] += 1
    return [{"Project": k, **{kk.replace("_", " ").title(): str(v) for kk, v in d.items()}}
            for k, d in sorted(projects.items())]


def do_create(args):
    title = args.title
    project = args.project if args.project else UNASSIGNED_DIR
    filename = f"{title}.md"
    project_path = os.path.join(NOTES_DIR, project)
    filepath = os.path.join(project_path, filename)
    rel_path = f"{project}/{filename}"
    if os.path.exists(filepath):
        print(json.dumps({"error": f"File already exists: {rel_path}"}))
        sys.exit(1)
    os.makedirs(project_path, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    fm = {
        "links": "", "tags": ["tasks"], "status": "open", "inform": "",
        "outcome": "", "project": project, "priority": args.priority or "",
        "due_date": args.due_date or "", "created_date": today,
        "completed_date": "", "description": args.description or title,
    }
    write_frontmatter(filepath, fm)
    print(json.dumps({"created": rel_path, "project": project}))


def do_update(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        sys.exit(1)
    updates = {}
    if args.status:
        updates["status"] = args.status
        if args.status.lower() == "done":
            updates["completed_date"] = datetime.now().strftime("%Y-%m-%d")
    if args.priority:
        updates["priority"] = args.priority
    if args.project:
        updates["project"] = args.project
    if args.due_date:
        updates["due_date"] = args.due_date
    if not updates:
        print(json.dumps({"error": "No updates specified"}))
        sys.exit(1)
    update_frontmatter_in_file(filepath, updates)
    print(json.dumps({"updated": args.file, "changes": updates}))


def do_close(args):
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        sys.exit(1)
    updates = {"status": "done", "completed_date": datetime.now().strftime("%Y-%m-%d")}
    update_frontmatter_in_file(filepath, updates)
    print(json.dumps({"updated": args.file, "changes": updates}))


def do_list_projects(_args):
    entries = get_all_entries()
    stats = _compute_stats(entries)
    print(json.dumps({"projects": stats, "total_projects": len(stats)}))


def do_dashboard(_args):
    entries = get_all_entries()
    today = datetime.now().date()
    soon = today + timedelta(days=7)
    by_project = defaultdict(list)
    for e in entries:
        by_project[e.get("Project", "") or "_unassigned"].append(e)

    projects_out, overdue, due_soon = [], [], []
    summary = {"total": 0, "open": 0, "in_progress": 0, "blocked": 0, "done": 0}
    PRIO = {"High Priority": 0, "Ongoing": 1, "To keep in Mind": 2, "Parked": 3}

    for pname in sorted(by_project):
        pentries = by_project[pname]
        counts = {"open": 0, "in_progress": 0, "blocked": 0, "done": 0}
        non_done = []
        for e in pentries:
            st = e.get("Status", "open").lower().strip()
            if st in ("done", "completed", "closed"):
                counts["done"] += 1
            elif st in ("in progress", "in_progress", "in-progress", "wip"):
                counts["in_progress"] += 1
            elif st in ("blocked", "waiting"):
                counts["blocked"] += 1
            else:
                counts["open"] += 1
            if st not in ("done", "completed", "closed"):
                non_done.append(e)
                due_str = e.get("Due Date", "").strip()
                if due_str:
                    try:
                        d = datetime.strptime(due_str, "%Y-%m-%d").date()
                        if d < today:
                            overdue.append(e)
                        elif d <= soon:
                            due_soon.append(e)
                    except ValueError:
                        pass

        top = sorted(non_done, key=lambda t: PRIO.get(t.get("Priority", "").strip(), 4))[:5]
        projects_out.append({
            "project": pname, **counts,
            "top_tasks": [compact({"title": t["Title"], "priority": t.get("Priority", ""),
                                    "due_date": t.get("Due Date", ""), "status": t.get("Status", "")}) for t in top],
        })
        summary["total"] += len(pentries)
        for k in ("open", "in_progress", "blocked", "done"):
            summary[k] += counts[k]

    print(json.dumps({"projects": projects_out, "overdue": overdue, "due_soon": due_soon, "summary": summary}))


def do_migrate(args):
    dry_run = args.dry_run
    migrated, skipped, errors = [], [], []
    if not os.path.isdir(NOTES_DIR):
        print(json.dumps({"error": f"Tasks directory not found: {NOTES_DIR}"}))
        return

    candidates = []
    for item in sorted(os.listdir(NOTES_DIR)):
        if item.startswith("."):
            continue
        item_path = os.path.join(NOTES_DIR, item)
        if os.path.isfile(item_path) and item.endswith(".md"):
            candidates.append((item_path, False, item_path))
        elif os.path.isdir(item_path):
            found_md = None
            try:
                for inner in os.listdir(item_path):
                    if inner.endswith(".md"):
                        inner_path = os.path.join(item_path, inner)
                        if os.path.isfile(inner_path):
                            fm, _ = parse_frontmatter(inner_path)
                            tags = fm.get("tags", "")
                            if (isinstance(tags, list) and "tasks" in tags) or \
                               (isinstance(tags, str) and "tasks" in tags):
                                found_md = inner_path
                                break
            except Exception as e:
                errors.append({"item": item, "error": str(e)})
                continue
            if found_md:
                fm, _ = parse_frontmatter(found_md)
                project = fm.get("project", "")
                if project and project == item:
                    skipped.append({"item": item, "reason": "already a project subfolder"})
                    continue
                candidates.append((item_path, True, found_md))

    for source_path, is_folder, md_filepath in candidates:
        item_name = os.path.basename(source_path)
        try:
            fm, body = parse_frontmatter(md_filepath)
            mtime_date = datetime.fromtimestamp(os.path.getmtime(md_filepath)).strftime("%Y-%m-%d")

            completed_val = fm.get("completed", "")
            if isinstance(completed_val, str):
                completed_val = completed_val.lower().strip()
            if completed_val == "true":
                fm["status"] = "done"
                fm["completed_date"] = mtime_date
            elif completed_val == "false":
                fm["status"] = "open"
            elif "status" not in fm:
                fm["status"] = "open"
            fm.pop("completed", None)

            if not fm.get("created_date"):
                fm["created_date"] = mtime_date
            for field in ("due_date", "description", "completed_date"):
                if field not in fm:
                    fm[field] = ""

            tags = fm.get("tags", "")
            if isinstance(tags, str):
                tags = [tags] if tags else []
            if "tasks" not in tags:
                tags.append("tasks")
            fm["tags"] = tags

            project = fm.get("project", "") or UNASSIGNED_DIR
            target_dir = os.path.join(NOTES_DIR, project)
            target_path = os.path.join(target_dir, item_name)
            if os.path.exists(target_path):
                skipped.append({"item": item_name, "reason": f"target exists: {target_path}"})
                continue

            info = {"item": item_name, "to": target_path, "project": project,
                    "status": fm.get("status", ""), "is_folder": is_folder}
            if dry_run:
                migrated.append(info)
            else:
                write_frontmatter(md_filepath, fm, body)
                os.makedirs(target_dir, exist_ok=True)
                shutil.move(source_path, target_path)
                if not is_folder:
                    bak = source_path + ".bak"
                    if os.path.exists(bak):
                        shutil.move(bak, target_path + ".bak")
                migrated.append(info)
        except Exception as e:
            errors.append({"item": item_name, "error": str(e)})

    print(json.dumps({"migrated": migrated, "skipped": skipped, "errors": errors,
                       "total": len(migrated), "dry_run": dry_run}))


def main():
    p = argparse.ArgumentParser(description="Backlog CLI")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("refresh")

    q = sub.add_parser("query")
    q.add_argument("--status")
    q.add_argument("--project")
    q.add_argument("--priority")
    q.add_argument("--search")
    q.add_argument("--due-before")
    q.add_argument("--due-after")

    s = sub.add_parser("stats")
    s.add_argument("--project")

    r = sub.add_parser("read")
    r.add_argument("file")

    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--project")
    c.add_argument("--priority")
    c.add_argument("--due-date")
    c.add_argument("--description")

    u = sub.add_parser("update")
    u.add_argument("file")
    u.add_argument("--status")
    u.add_argument("--priority")
    u.add_argument("--project")
    u.add_argument("--due-date")

    cl = sub.add_parser("close")
    cl.add_argument("file")

    sub.add_parser("list-projects")
    sub.add_parser("dashboard")

    m = sub.add_parser("migrate")
    m.add_argument("--dry-run", action="store_true")

    args = p.parse_args()
    cmds = {
        "refresh": do_refresh, "query": do_query, "stats": do_stats,
        "read": do_read, "create": do_create, "update": do_update,
        "close": do_close, "list-projects": do_list_projects,
        "dashboard": do_dashboard, "migrate": do_migrate,
    }
    if args.command in cmds:
        cmds[args.command](args)
    else:
        p.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
