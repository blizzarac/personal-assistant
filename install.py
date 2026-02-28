#!/usr/bin/env python3
"""Cross-platform installer for personal-assistant skills."""

import os
import sys
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
SKILLS_DIR = os.path.join(HOME, ".claude", "skills")
DATA_ROOT = os.path.join(HOME, ".local", "share", "assistant")
SKILLS = ["assistant", "journal", "tasks", "meeting", "person"]
DATA_SKILLS = ["journal", "tasks", "meeting", "person"]


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
