#!/usr/bin/env python3
"""Cross-platform installer for personal-assistant skills."""

import os
import subprocess
import sys
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SKILLS_DIR = os.path.join(HOME, ".claude", "skills")
DATA_ROOT = os.path.join(HOME, ".local", "share", "assistant")
SKILLS = ["assistant", "journal", "backlog", "meeting", "person", "calendar"]
DATA_SKILLS = ["journal", "backlog", "meeting", "person", "calendar"]

QMD_COLLECTIONS = {
    "journal": os.path.join(DATA_ROOT, "journal"),
    "backlog": os.path.join(DATA_ROOT, "backlog"),
    "meeting": os.path.join(DATA_ROOT, "meeting"),
    "person": os.path.join(DATA_ROOT, "person"),
    "calendar": os.path.join(DATA_ROOT, "calendar"),
}

QMD_CONTEXTS = {
    "journal": "Daily journal entries and reflections, organized by year",
    "backlog": "Task backlog organized by project folders, with priorities and due dates",
    "meeting": "Meeting notes with attendees, topics, decisions, and action items",
    "person": "People directory with relationships, birthdays, and how we met",
    "calendar": "Google Calendar events synced locally, with dates, attendees, and locations",
}


def setup_qmd():
    """Register QMD collections for all data skills."""
    if not shutil.which("qmd"):
        print("  [skip] qmd -- not installed (install with: npm install -g @tobilu/qmd)")
        return

    print("  Setting up QMD collections...")
    try:
        result = subprocess.run(["qmd", "collection", "list"],
                                capture_output=True, text=True, timeout=10)
        existing = result.stdout
    except Exception:
        existing = ""

    for name, path in QMD_COLLECTIONS.items():
        if name in existing:
            print(f"  [skip] qmd/{name} -- collection already exists")
        else:
            try:
                subprocess.run(["qmd", "collection", "add", path, "--name", name],
                               capture_output=True, text=True, timeout=10, check=True)
                print(f"  [ok]   qmd/{name} -- collection added")
            except Exception:
                print(f"  [warn] qmd/{name} -- failed to add collection")

        # Add context (idempotent)
        ctx = QMD_CONTEXTS[name]
        try:
            subprocess.run(["qmd", "context", "add", f"qmd://{name}", ctx],
                           capture_output=True, text=True, timeout=10)
        except Exception:
            pass

    print("  Embedding QMD collections...")
    try:
        subprocess.run(["qmd", "embed"], capture_output=True, text=True, timeout=120, check=True)
        print("  [ok]   qmd -- embedding complete")
    except Exception:
        print("  [warn] qmd -- embedding failed (run 'qmd embed' manually)")


def remove_qmd():
    """Remove QMD collections."""
    if not shutil.which("qmd"):
        return

    for name in QMD_COLLECTIONS:
        try:
            subprocess.run(["qmd", "collection", "remove", name],
                           capture_output=True, text=True, timeout=10, check=True)
            print(f"  [ok]   qmd/{name} -- collection removed")
        except Exception:
            print(f"  [skip] qmd/{name} -- not found")


def install():
    print("Installing personal-assistant...")
    print()

    os.makedirs(SKILLS_DIR, exist_ok=True)

    for skill in SKILLS:
        target = os.path.join(SKILLS_DIR, skill)
        source = os.path.join(SCRIPT_DIR, "skills", skill)

        if os.path.islink(target):
            existing = os.readlink(target)
            if os.path.normpath(existing) == os.path.normpath(source):
                print(f"  [skip] {skill} -- already linked")
            else:
                print(f"  [warn] {skill} -- symlink exists pointing to {existing}, skipping")
        elif os.path.exists(target):
            print(f"  [warn] {skill} -- {target} already exists (not a symlink), skipping")
        else:
            try:
                os.symlink(source, target, target_is_directory=True)
                print(f"  [ok]   {skill} -- linked")
            except OSError as e:
                if sys.platform == "win32":
                    print(f"  [fail] {skill} -- symlink failed: {e}")
                    print(f"         Enable Developer Mode in Windows Settings > Update & Security > For Developers")
                    print(f"         Or run this script as Administrator")
                    return
                raise

    print()

    for skill in DATA_SKILLS:
        d = os.path.join(DATA_ROOT, skill)
        if os.path.isdir(d):
            print(f"  [skip] data/{skill} -- already exists")
        else:
            os.makedirs(d, exist_ok=True)
            print(f"  [ok]   data/{skill} -- created")

    print()

    setup_qmd()

    print()
    print(f"Done! Skills installed to {SKILLS_DIR}")
    print(f"Data directories at {DATA_ROOT}")


def uninstall():
    print("Uninstalling personal-assistant...")
    print()

    for skill in SKILLS:
        target = os.path.join(SKILLS_DIR, skill)
        if os.path.islink(target):
            os.remove(target)
            print(f"  [ok]   {skill} -- symlink removed")
        elif os.path.exists(target):
            print(f"  [warn] {skill} -- {target} is not a symlink, skipping")
        else:
            print(f"  [skip] {skill} -- not found")

    print()

    remove_qmd()

    print()
    print(f"Done! Symlinks removed. Data in {DATA_ROOT} was NOT touched.")


def usage():
    print(f"Usage: python {sys.argv[0]} [--uninstall]")
    print()
    print(f"Install:   python {sys.argv[0]}")
    print(f"Uninstall: python {sys.argv[0]} --uninstall")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        install()
    elif sys.argv[1] in ("--uninstall",):
        uninstall()
    elif sys.argv[1] in ("--help", "-h"):
        usage()
    else:
        print(f"Unknown option: {sys.argv[1]}")
        usage()
        sys.exit(1)
