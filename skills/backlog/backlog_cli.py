#!/usr/bin/env python3
"""CLI tool for managing the tasks index and queries."""

import argparse
import json
import os
import re
import shutil
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
INDEX_PATH = os.path.join(NOTES_DIR, CFG["index_file"])
UNASSIGNED_DIR = CFG.get("unassigned_dir", "_unassigned")
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
    "Priority", "due_date", "created_date", "completed_date", "description",
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
# Markdown table I/O
# ---------------------------------------------------------------------------

ENTRY_HEADERS = ["Title", "File", "Project", "Status", "Priority", "Due Date", "Created", "Completed", "Description"]
STATS_HEADERS = ["Project", "Open", "In Progress", "Blocked", "Done", "Total"]

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
            if in_table and (line.startswith("|---") or line.startswith("| ---")):
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
    """Write the full tasks index file with Entries and Project Stats tables."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Tasks Index",
        f"Last updated: {today}",
        "",
        "## Entries",
        "",
        "| " + " | ".join(ENTRY_HEADERS) + " |",
        "| " + " | ".join(["------"] * len(ENTRY_HEADERS)) + " |",
    ]
    for row in sorted(entries, key=lambda r: (r.get("Project", ""), r.get("Title", ""))):
        vals = [row.get(h, "") for h in ENTRY_HEADERS]
        lines.append("| " + " | ".join(vals) + " |")

    lines.append("")

    stats = compute_project_stats(entries)
    lines.append("## Project Stats")
    lines.append("")
    lines.append("| " + " | ".join(STATS_HEADERS) + " |")
    lines.append("| " + " | ".join(["------"] * len(STATS_HEADERS)) + " |")
    for row in sorted(stats, key=lambda r: r.get("Project", "")):
        vals = [row.get(h, "") for h in STATS_HEADERS]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")

    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

# ---------------------------------------------------------------------------
# File discovery
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
    """Create an index entry dict from a task file."""
    fm = parse_frontmatter(abs_path)
    filename = os.path.basename(rel_path)

    # Title from filename without .md extension
    title = filename.replace(".md", "")

    # Project: from frontmatter or inferred from directory
    project = fm.get("project", "")
    if not project:
        # First path component is the project directory
        parts = rel_path.split("/")
        project = parts[0] if parts else ""

    # Status: support new 'status' field and old 'completed: true/false' for backwards compat
    status = fm.get("status", "")
    if not status:
        completed = fm.get("completed", "")
        if isinstance(completed, str):
            completed = completed.lower().strip()
        if completed == "true":
            status = "done"
        elif completed == "false":
            status = "open"
        else:
            status = "open"

    priority = fm.get("Priority", fm.get("priority", ""))
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

    # Description: from frontmatter, or first 80 chars of body
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
            # open, or any custom status text (e.g. "with Malte") counts as open
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

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_refresh(args):
    """Diff filesystem vs index, add new files, remove deleted files, rewrite index."""
    disk_files = discover_files()
    entries = read_index_table(INDEX_PATH, "## Entries")
    indexed_files = {r["File"] for r in entries}
    disk_set = set(disk_files.keys())

    added = disk_set - indexed_files
    removed = indexed_files - disk_set

    if not added and not removed:
        print(json.dumps({"added": [], "removed": [], "total": len(entries)}))
        return

    if removed:
        entries = [e for e in entries if e["File"] not in removed]

    added_list = []
    for rel_path in sorted(added):
        try:
            entry = entry_from_file(rel_path, disk_files[rel_path])
            entries.append(entry)
            added_list.append(rel_path)
        except Exception as e:
            sys.stderr.write(f"Error parsing {rel_path}: {e}\n")

    write_index(entries)
    print(json.dumps({"added": added_list, "removed": sorted(removed), "total": len(entries)}))

def cmd_query(args):
    """Filter tasks from the index. Supports combining multiple filters."""
    entries = read_index_table(INDEX_PATH, "## Entries")

    if args.status:
        status = args.status.lower()
        entries = [e for e in entries if e.get("Status", "").lower() == status]
    if args.project:
        project = args.project.lower()
        entries = [e for e in entries if project in e.get("Project", "").lower()]
    if args.priority:
        priority = args.priority
        entries = [e for e in entries if e.get("Priority", "") == priority]
    if args.search:
        term = args.search.lower()
        entries = [e for e in entries if term in e.get("Title", "").lower() or term in e.get("Description", "").lower()]
    if args.due_before:
        entries = [e for e in entries if e.get("Due Date", "") and e.get("Due Date", "") < args.due_before]
    if args.due_after:
        entries = [e for e in entries if e.get("Due Date", "") and e.get("Due Date", "") > args.due_after]

    print(json.dumps({"results": entries, "count": len(entries)}))

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
    entries = read_index_table(INDEX_PATH, "## Entries")

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
        "Priority": "",
        "due_date": "",
        "created_date": today,
        "completed_date": "",
        "description": "",
    }
    if args.priority:
        fm["Priority"] = args.priority
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
        updates["Priority"] = args.priority
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
    stats_rows = read_index_table(INDEX_PATH, "## Project Stats")
    projects = []
    for row in stats_rows:
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
    entries = read_index_table(INDEX_PATH, "## Entries")
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

    # Collect candidates: (source_path, is_folder, md_filepath)
    # source_path = what to move (file or folder)
    # md_filepath  = the .md file to parse/update frontmatter in
    candidates = []

    for item in sorted(os.listdir(NOTES_DIR)):
        if item.startswith("."):
            continue
        if item in EXCLUDE:
            continue
        item_path = os.path.join(NOTES_DIR, item)

        # Case 1: simple .md file in root
        if os.path.isfile(item_path) and item.endswith(".md"):
            candidates.append((item_path, False, item_path))

        # Case 2: folder-style task in root
        elif os.path.isdir(item_path):
            # Look for any .md file inside that has the 'tasks' tag
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
                # Check if this folder IS already a project subfolder
                # (i.e. it contains subfolders that are tasks, not a task itself)
                fm = parse_frontmatter(found_md)
                project = fm.get("project", "")
                if project and project == item:
                    # Already in a project subfolder (project == folder name), skip
                    skipped.append({"item": item, "reason": "already a project subfolder"})
                    continue
                candidates.append((item_path, True, found_md))

    # Process each candidate
    for source_path, is_folder, md_filepath in candidates:
        item_name = os.path.basename(source_path)
        try:
            # Parse frontmatter
            fm = parse_frontmatter(md_filepath)

            # Read full file content to preserve body
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

            # Get file modification time for date fields
            mtime = os.path.getmtime(md_filepath)
            mtime_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

            # Convert completed -> status
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

            # Remove old completed field
            if "completed" in fm:
                del fm["completed"]

            # Add created_date from mtime if not present
            if not fm.get("created_date"):
                fm["created_date"] = mtime_date

            # Add missing fields as empty strings
            for field in ("due_date", "description", "completed_date"):
                if field not in fm:
                    fm[field] = ""

            # Ensure tags contains 'tasks'
            tags = fm.get("tags", "")
            if isinstance(tags, str):
                if tags:
                    tags = [tags]
                else:
                    tags = []
            if "tasks" not in tags:
                tags.append("tasks")
            fm["tags"] = tags

            # Determine target directory
            project = fm.get("project", "")
            if not project:
                project = UNASSIGNED_DIR
            target_dir = os.path.join(NOTES_DIR, project)
            target_path = os.path.join(target_dir, item_name)

            # Conflict check
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
                # Update frontmatter in the file before moving
                write_frontmatter(md_filepath, fm, body)

                # Create target directory if needed
                os.makedirs(target_dir, exist_ok=True)

                # Move the file or folder
                shutil.move(source_path, target_path)

                # Also move .bak file if it exists (for simple .md files)
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
    parser = argparse.ArgumentParser(description="Task CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("refresh", help="Diff filesystem vs index, update index")

    q = sub.add_parser("query", help="Query and filter tasks")
    q.add_argument("--status", help="Filter by status (open/in-progress/done/blocked)")
    q.add_argument("--project", help="Filter by project name (case-insensitive partial match)")
    q.add_argument("--priority", help="Filter by exact priority value")
    q.add_argument("--search", help="Search titles and descriptions (case-insensitive)")
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
