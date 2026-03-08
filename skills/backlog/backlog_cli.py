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
UNASSIGNED_DIR = CFG.get("unassigned_dir", "_unassigned")
COLLECTION = CFG.get("collection", "backlog")
EXCLUDE = CFG.get("exclude", [])
if isinstance(EXCLUDE, str):
    EXCLUDE = [EXCLUDE]

# ---------------------------------------------------------------------------
# QMD helpers
# ---------------------------------------------------------------------------


def qmd_available():
    """Check if qmd is installed."""
    return shutil.which("qmd") is not None


def qmd_search(query_text, n=20):
    """Run qmd query (hybrid search) and return parsed JSON results."""
    cmd = ["qmd", "query", "-c", COLLECTION, "-n", str(n), "--json", query_text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def qmd_embed():
    """Re-embed the QMD collection."""
    cmd = ["qmd", "embed"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def qmd_ensure_collection():
    """Ensure the QMD collection exists for the backlog data directory."""
    # Check if collection already exists
    try:
        result = subprocess.run(
            ["qmd", "collection", "list"], capture_output=True, text=True, timeout=10
        )
        if COLLECTION in result.stdout:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    # Add collection
    try:
        result = subprocess.run(
            ["qmd", "collection", "add", NOTES_DIR, "--name", COLLECTION],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            # Add context description
            subprocess.run(
                ["qmd", "context", "add", f"qmd://{COLLECTION}",
                 "Task backlog with project-based organization. Each task has YAML frontmatter with status, priority, due_date, and project fields."],
                capture_output=True, text=True, timeout=10,
            )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


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
# Frontmatter writing
# ---------------------------------------------------------------------------

FRONTMATTER_FIELD_ORDER = [
    "links", "tags", "status", "inform", "outcome", "project",
    "priority", "due_date", "created_date", "completed_date", "description",
]


def _write_fm_field(lines, key, value):
    """Append a single frontmatter field to lines list."""
    if isinstance(value, list):
        lines.append(f"{key}:")
        for item in value:
            lines.append(f"  - {item}")
    elif value == "" or value is None:
        lines.append(f"{key}:")
    else:
        lines.append(f"{key}: {value}")


def write_frontmatter(filepath, fm, body=""):
    """Write a markdown file with YAML frontmatter, preserving field order."""
    lines = ["---"]
    written_keys = set()
    for key in FRONTMATTER_FIELD_ORDER:
        if key in fm:
            _write_fm_field(lines, key, fm[key])
            written_keys.add(key)
    # Write any extra fields not in the standard order
    for key in fm:
        if key not in written_keys:
            _write_fm_field(lines, key, fm[key])
    lines.append("---")
    if body:
        lines.append(body)
    else:
        lines.append("")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def update_frontmatter_in_file(filepath, updates):
    """Read a file, parse frontmatter and body, apply updates, rewrite."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    # Extract body (everything after frontmatter)
    body = ""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            body = content[end + 3:]
            # Strip exactly one leading newline if present
            if body.startswith("\n"):
                body = body[1:]
    else:
        body = content
    fm.update(updates)
    write_frontmatter(filepath, fm, body)


# ---------------------------------------------------------------------------
# File discovery (replaces index-based lookups)
# ---------------------------------------------------------------------------

def discover_files():
    """Find all task .md files in project subfolders of the tasks directory.

    Handles two structures:
      - tasks/Project/Task Name.md           (simple file)
      - tasks/Project/Task Name/Task Name.md (folder-style with attachments)

    Skips directories starting with '.' and files in the EXCLUDE list.
    """
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

            # Case 1: simple file — tasks/Project/Task Name.md
            if os.path.isfile(item_path) and item.endswith(".md") and item not in EXCLUDE:
                rel_path = f"{project_dir}/{item}"
                files[rel_path] = item_path

            # Case 2: folder-style — tasks/Project/Task Name/Task Name.md
            elif os.path.isdir(item_path):
                inner_md = os.path.join(item_path, item + ".md")
                if os.path.isfile(inner_md) and (item + ".md") not in EXCLUDE:
                    rel_path = f"{project_dir}/{item}/{item}.md"
                    files[rel_path] = inner_md
    return files


def entry_from_file(rel_path, abs_path):
    """Create an entry dict from a task file."""
    fm = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)

    title = filename.replace(".md", "")

    project = fm.get("project", "")
    if not project:
        parts = rel_path.split("/")
        project = parts[0] if parts else ""

    status = fm.get("status", "")
    if not status:
        completed = fm.get("completed", "")
        if isinstance(completed, str):
            completed = completed.lower().strip()
        if completed == "true":
            status = "done"
        else:
            status = "open"

    priority = fm.get("priority", fm.get("Priority", ""))
    if not priority:
        priority = ""

    due_date = fm.get("due", fm.get("due_date", ""))
    if not due_date:
        due_date = ""

    created = fm.get("created_date", fm.get("created", ""))
    if not created:
        created = ""

    completed_date = fm.get("completed_date", "")
    if not completed_date:
        completed_date = ""

    description = fm.get("description", "")
    if not description:
        description = fm.get("outcome", "")
    if not description:
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
        "Title": title,
        "File": rel_path,
        "Project": str(project),
        "Status": str(status),
        "Priority": str(priority),
        "Due Date": str(due_date),
        "Created": str(created),
        "Completed": str(completed_date),
        "Description": str(description),
    }


def get_all_entries():
    """Scan all task files and return entry dicts."""
    files = discover_files()
    entries = []
    for rel_path, abs_path in sorted(files.items()):
        try:
            entries.append(entry_from_file(rel_path, abs_path))
        except Exception as e:
            sys.stderr.write(f"Error parsing {rel_path}: {e}\n")
    return entries


# ---------------------------------------------------------------------------
# Project stats
# ---------------------------------------------------------------------------

def compute_project_stats(entries):
    """Compute per-project counts of open/in-progress/blocked/done tasks."""
    projects = defaultdict(lambda: {"open": 0, "in_progress": 0, "blocked": 0, "done": 0, "total": 0})
    for e in entries:
        project = e.get("Project", "") or "_unassigned"
        status = e.get("Status", "open").lower().strip()
        projects[project]["total"] += 1
        if status in ("done", "completed", "closed"):
            projects[project]["done"] += 1
        elif status in ("in progress", "in_progress", "in-progress", "wip"):
            projects[project]["in_progress"] += 1
        elif status in ("blocked", "waiting"):
            projects[project]["blocked"] += 1
        else:
            projects[project]["open"] += 1

    stats = []
    for project in sorted(projects.keys()):
        data = projects[project]
        stats.append({
            "Project": project,
            "Open": str(data["open"]),
            "In Progress": str(data["in_progress"]),
            "Blocked": str(data["blocked"]),
            "Done": str(data["done"]),
            "Total": str(data["total"]),
        })
    return stats


STATS_HEADERS = ["Project", "Open", "In Progress", "Blocked", "Done", "Total"]

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    """Update QMD index by re-embedding the collection."""
    if not qmd_available():
        print(json.dumps({"error": "qmd is not installed. Install with: npm install -g @tobilu/qmd"}))
        sys.exit(1)

    qmd_ensure_collection()
    success = qmd_embed()
    if success:
        total = len(discover_files())
        print(json.dumps({"status": "ok", "indexed": True, "total": total}))
    else:
        print(json.dumps({"status": "error", "message": "qmd embed failed"}))
        sys.exit(1)


def cmd_query(args):
    """Filter tasks. Uses QMD for text search, direct file scan for structured filters."""
    # Text search via QMD
    if args.search and qmd_available():
        qmd_results = qmd_search(args.search)
        if qmd_results is not None:
            # Map QMD results back to entries with frontmatter
            files = discover_files()
            entries = []
            seen = set()
            for result in qmd_results:
                # QMD returns paths relative to collection root
                path = result.get("path", "")
                if path in files and path not in seen:
                    seen.add(path)
                    entry = entry_from_file(path, files[path])
                    entry["_score"] = result.get("score", 0)
                    entries.append(entry)

            # Apply structured filters on top of search results
            entries = _apply_structured_filters(entries, args)
            print(json.dumps({"results": entries, "count": len(entries), "source": "qmd"}))
            return

    # Fallback: scan all files and filter
    entries = get_all_entries()

    # Text search fallback (substring match) if qmd unavailable
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries if term in e.get("Title", "").lower() or term in e.get("Description", "").lower()]

    entries = _apply_structured_filters(entries, args)
    source = "scan"
    if args.search:
        source = "scan-fallback"
    print(json.dumps({"results": entries, "count": len(entries), "source": source}))


def _apply_structured_filters(entries, args):
    """Apply structured frontmatter filters to a list of entries."""
    if args.status:
        status = args.status.lower()
        entries = [e for e in entries if e.get("Status", "").lower() == status]
    if args.project:
        project = args.project.lower()
        entries = [e for e in entries if project in e.get("Project", "").lower()]
    if args.priority:
        priority = args.priority
        entries = [e for e in entries if e.get("Priority", "") == priority]
    if args.due_before:
        entries = [e for e in entries if e.get("Due Date", "") and e.get("Due Date", "") < args.due_before]
    if args.due_after:
        entries = [e for e in entries if e.get("Due Date", "") and e.get("Due Date", "") > args.due_after]
    return entries


def cmd_read(args):
    """Read a specific task file by relative path."""
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        # Search project directories
        for project_dir in os.listdir(NOTES_DIR):
            project_path = os.path.join(NOTES_DIR, project_dir)
            if not os.path.isdir(project_path) or project_dir.startswith("."):
                continue
            candidate = os.path.join(project_path, args.file)
            if os.path.exists(candidate):
                filepath = candidate
                break
            # Also check folder-style: Project/TaskName/TaskName.md
            name_no_ext = args.file.replace(".md", "") if args.file.endswith(".md") else args.file
            candidate2 = os.path.join(project_path, name_no_ext, args.file)
            if os.path.exists(candidate2):
                filepath = candidate2
                break
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = parse_frontmatter(filepath)
    print(json.dumps({"file": args.file, "frontmatter": fm, "content": content}))


def cmd_stats(args):
    """Show task statistics. Optional --project filter."""
    entries = get_all_entries()

    if args.project:
        project = args.project.lower()
        entries = [e for e in entries if project in e.get("Project", "").lower()]

    stats = compute_project_stats(entries)

    print(json.dumps({
        "total_entries": len(entries),
        "project_stats": stats,
    }))


def cmd_create(args):
    """Create a new task file with frontmatter."""
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
        "links": "",
        "tags": ["tasks"],
        "status": "open",
        "inform": "",
        "outcome": "",
        "project": project,
        "priority": "",
        "due_date": "",
        "created_date": today,
        "completed_date": "",
        "description": "",
    }
    if args.priority:
        fm["priority"] = args.priority
    if args.due_date:
        fm["due_date"] = args.due_date
    if args.description:
        fm["description"] = args.description
    else:
        fm["description"] = title

    write_frontmatter(filepath, fm)
    print(json.dumps({"created": rel_path, "project": project}))


def cmd_update(args):
    """Update a task's frontmatter fields."""
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


def cmd_close(args):
    """Mark a task as done (shortcut for update --status done)."""
    filepath = os.path.join(NOTES_DIR, args.file)
    if not os.path.exists(filepath):
        print(json.dumps({"error": f"File not found: {args.file}"}))
        sys.exit(1)

    updates = {
        "status": "done",
        "completed_date": datetime.now().strftime("%Y-%m-%d"),
    }
    update_frontmatter_in_file(filepath, updates)
    print(json.dumps({"updated": args.file, "changes": updates}))


def cmd_list_projects(args):
    """List all project folders with task counts per status."""
    entries = get_all_entries()
    stats = compute_project_stats(entries)
    projects = []
    for row in stats:
        projects.append({
            "project": row.get("Project", ""),
            "open": int(row.get("Open", "0") or "0"),
            "in_progress": int(row.get("In Progress", "0") or "0"),
            "blocked": int(row.get("Blocked", "0") or "0"),
            "done": int(row.get("Done", "0") or "0"),
            "total": int(row.get("Total", "0") or "0"),
        })
    print(json.dumps({"projects": projects, "total_projects": len(projects)}))


def cmd_dashboard(args):
    """Overview output grouped by project, sorted by priority."""
    entries = get_all_entries()
    today = datetime.now().date()
    soon_cutoff = today + timedelta(days=7)

    # Group entries by project
    by_project = defaultdict(list)
    for e in entries:
        by_project[e.get("Project", "") or "_unassigned"].append(e)

    projects_out = []
    all_overdue = []
    all_due_soon = []
    summary = {"total": 0, "open": 0, "in_progress": 0, "blocked": 0, "done": 0}

    for project_name in sorted(by_project.keys()):
        project_entries = by_project[project_name]
        counts = {"open": 0, "in_progress": 0, "blocked": 0, "done": 0}

        non_done = []
        for e in project_entries:
            status = e.get("Status", "open").lower().strip()
            if status in ("done", "completed", "closed"):
                counts["done"] += 1
            elif status in ("in progress", "in_progress", "in-progress", "wip"):
                counts["in_progress"] += 1
            elif status in ("blocked", "waiting"):
                counts["blocked"] += 1
            else:
                counts["open"] += 1

            # Collect non-done tasks
            if status not in ("done", "completed", "closed"):
                non_done.append(e)

                # Check due dates for overdue / due_soon
                due_str = e.get("Due Date", "").strip()
                if due_str:
                    try:
                        due_date = datetime.strptime(due_str, "%Y-%m-%d").date()
                        if due_date < today:
                            all_overdue.append(e)
                        elif due_date <= soon_cutoff:
                            all_due_soon.append(e)
                    except ValueError:
                        pass

        # Top 5 highest-priority non-done tasks
        PRIORITY_ORDER = {"High Priority": 0, "Ongoing": 1, "To keep in Mind": 2, "Parked": 3}
        def priority_sort_key(task):
            p = task.get("Priority", "").strip()
            return PRIORITY_ORDER.get(p, 4)

        non_done_sorted = sorted(non_done, key=priority_sort_key)
        top_tasks = []
        for t in non_done_sorted[:5]:
            top_tasks.append({
                "title": t.get("Title", ""),
                "priority": t.get("Priority", ""),
                "due_date": t.get("Due Date", ""),
                "status": t.get("Status", ""),
            })

        projects_out.append({
            "project": project_name,
            "open": counts["open"],
            "in_progress": counts["in_progress"],
            "blocked": counts["blocked"],
            "done": counts["done"],
            "top_tasks": top_tasks,
        })

        summary["total"] += len(project_entries)
        summary["open"] += counts["open"]
        summary["in_progress"] += counts["in_progress"]
        summary["blocked"] += counts["blocked"]
        summary["done"] += counts["done"]

    print(json.dumps({
        "projects": projects_out,
        "overdue": all_overdue,
        "due_soon": all_due_soon,
        "summary": summary,
    }))


def cmd_migrate(args):
    """Migrate old-format task files from tasks root into project subfolders.

    Scans for:
      - .md files in the root of the tasks directory (old flat format)
      - folder-style tasks in root (directories containing a .md with 'tasks' tag)

    For each file: updates frontmatter (completed -> status, adds missing fields),
    then moves into tasks/<project>/ or tasks/_unassigned/.
    """
    dry_run = args.dry_run
    migrated = []
    skipped = []
    errors = []

    if not os.path.isdir(NOTES_DIR):
        print(json.dumps({"error": f"Tasks directory not found: {NOTES_DIR}"}))
        return

    candidates = []

    for item in sorted(os.listdir(NOTES_DIR)):
        if item.startswith("."):
            continue
        if item in EXCLUDE:
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
                            fm = parse_frontmatter(inner_path)
                            tags = fm.get("tags", "")
                            if isinstance(tags, list) and "tasks" in tags:
                                found_md = inner_path
                                break
                            elif isinstance(tags, str) and "tasks" in tags:
                                found_md = inner_path
                                break
            except Exception as e:
                errors.append({"item": item, "error": str(e)})
                continue

            if found_md:
                fm = parse_frontmatter(found_md)
                project = fm.get("project", "")
                if project and project == item:
                    skipped.append({"item": item, "reason": "already a project subfolder"})
                    continue
                candidates.append((item_path, True, found_md))

    for source_path, is_folder, md_filepath in candidates:
        item_name = os.path.basename(source_path)
        try:
            fm = parse_frontmatter(md_filepath)

            with open(md_filepath, "r", encoding="utf-8") as f:
                content = f.read()
            body = ""
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    body = content[end + 3:]
                    if body.startswith("\n"):
                        body = body[1:]
            else:
                body = content

            mtime = os.path.getmtime(md_filepath)
            mtime_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

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

            if "completed" in fm:
                del fm["completed"]

            if not fm.get("created_date"):
                fm["created_date"] = mtime_date

            for field in ("due_date", "description", "completed_date"):
                if field not in fm:
                    fm[field] = ""

            tags = fm.get("tags", "")
            if isinstance(tags, str):
                if tags:
                    tags = [tags]
                else:
                    tags = []
            if "tasks" not in tags:
                tags.append("tasks")
            fm["tags"] = tags

            project = fm.get("project", "")
            if not project:
                project = UNASSIGNED_DIR
            target_dir = os.path.join(NOTES_DIR, project)
            target_path = os.path.join(target_dir, item_name)

            if os.path.exists(target_path):
                skipped.append({"item": item_name, "reason": f"target already exists: {target_path}"})
                continue

            if dry_run:
                migrated.append({
                    "item": item_name,
                    "from": source_path,
                    "to": target_path,
                    "project": project,
                    "status": fm.get("status", ""),
                    "is_folder": is_folder,
                })
            else:
                write_frontmatter(md_filepath, fm, body)
                os.makedirs(target_dir, exist_ok=True)
                shutil.move(source_path, target_path)

                if not is_folder:
                    bak_path = source_path + ".bak"
                    if os.path.exists(bak_path):
                        bak_target = target_path + ".bak"
                        shutil.move(bak_path, bak_target)

                migrated.append({
                    "item": item_name,
                    "from": source_path,
                    "to": target_path,
                    "project": project,
                    "status": fm.get("status", ""),
                    "is_folder": is_folder,
                })

        except Exception as e:
            errors.append({"item": item_name, "error": str(e)})

    print(json.dumps({
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "total": len(migrated),
        "dry_run": dry_run,
    }))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backlog CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Re-embed QMD collection for search")

    q = sub.add_parser("query", help="Query and filter tasks")
    q.add_argument("--status", help="Filter by status (open/in-progress/done/blocked)")
    q.add_argument("--project", help="Filter by project name (case-insensitive partial match)")
    q.add_argument("--priority", help="Filter by exact priority value")
    q.add_argument("--search", help="Search titles and descriptions (uses QMD when available)")
    q.add_argument("--due-before", help="Tasks due before date (YYYY-MM-DD)")
    q.add_argument("--due-after", help="Tasks due after date (YYYY-MM-DD)")

    s = sub.add_parser("stats", help="Show task statistics")
    s.add_argument("--project", help="Filter stats by project")

    r = sub.add_parser("read", help="Read a task file")
    r.add_argument("file", help="Filename or relative path")

    c = sub.add_parser("create", help="Create a new task file")
    c.add_argument("--title", required=True, help="Task title (becomes filename)")
    c.add_argument("--project", help="Project directory name")
    c.add_argument("--priority", help="Priority value")
    c.add_argument("--due-date", help="Due date (YYYY-MM-DD)")
    c.add_argument("--description", help="Task description")

    u = sub.add_parser("update", help="Update a task's frontmatter")
    u.add_argument("file", help="Relative path to task file")
    u.add_argument("--status", help="New status value")
    u.add_argument("--priority", help="New priority value")
    u.add_argument("--project", help="New project value")
    u.add_argument("--due-date", help="New due date (YYYY-MM-DD)")

    cl = sub.add_parser("close", help="Mark a task as done")
    cl.add_argument("file", help="Relative path to task file")

    sub.add_parser("list-projects", help="List all projects with task counts")

    sub.add_parser("dashboard", help="Overview grouped by project, sorted by priority")

    m = sub.add_parser("migrate", help="Migrate old-format task files into project subfolders")
    m.add_argument("--dry-run", action="store_true", help="Show what would happen without making changes")

    args = parser.parse_args()
    commands = {
        "refresh": cmd_refresh,
        "query": cmd_query,
        "stats": cmd_stats,
        "read": cmd_read,
        "create": cmd_create,
        "update": cmd_update,
        "close": cmd_close,
        "list-projects": cmd_list_projects,
        "dashboard": cmd_dashboard,
        "migrate": cmd_migrate,
    }
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == "__main__":
    main()
