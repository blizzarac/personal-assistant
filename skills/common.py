"""Shared utilities for personal-assistant CLI tools."""

import json
import os
import shutil
import subprocess


def load_config(script_dir):
    """Parse a simple YAML config file (no external deps)."""
    cfg = {}
    with open(os.path.join(script_dir, "config.yaml"), "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line and not line.startswith("-"):
                key, val = line.split(":", 1)
                key, val = key.strip(), val.strip()
                cfg[key] = [] if val == "" else val
            elif line.startswith("- ") and cfg:
                last_key = list(cfg.keys())[-1]
                if isinstance(cfg[last_key], list):
                    cfg[last_key].append(line[2:].strip())
    return cfg


def parse_frontmatter(filepath):
    """Parse YAML frontmatter from a markdown file. Returns (fm_dict, body_str)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    fm = {}
    if not content.startswith("---"):
        return fm, content
    end = content.find("---", 3)
    if end == -1:
        return fm, content
    block = content[3:end]
    body = content[end + 3:]
    if body.startswith("\n"):
        body = body[1:]
    current_key = None
    for line in block.split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("- ") and current_key:
            if current_key not in fm:
                fm[current_key] = []
            if not isinstance(fm[current_key], list):
                fm[current_key] = [fm[current_key]] if fm[current_key] else []
            fm[current_key].append(s[2:].strip().strip('"'))
        elif ":" in s:
            key, val = s.split(":", 1)
            key, val = key.strip(), val.strip()
            current_key = key
            fm[key] = "" if val == "" else val
    return fm, body


def qmd_available():
    """Check if qmd CLI is installed."""
    return shutil.which("qmd") is not None


def qmd_search(collection, query_text, n=20):
    """Run qmd query and return parsed JSON results, or None on failure."""
    cmd = ["qmd", "query", "-c", collection, "-n", str(n), "--json", query_text]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def qmd_embed():
    """Re-embed all QMD collections. Returns True on success."""
    try:
        result = subprocess.run(
            ["qmd", "embed"], capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def cmd_refresh(discover_fn):
    """Generic refresh handler: run qmd embed, report file count."""
    if not qmd_available():
        print(json.dumps({"error": "qmd not installed"}))
        return False
    if qmd_embed():
        print(json.dumps({"status": "ok", "total": len(discover_fn())}))
        return True
    print(json.dumps({"status": "error", "message": "qmd embed failed"}))
    return False


def compact(d):
    """Remove keys with empty-string values from a dict (reduces JSON output tokens)."""
    return {k: v for k, v in d.items() if v != ""}
