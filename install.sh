#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
DATA_ROOT="$HOME/.local/share/assistant"
SKILLS=(assistant journal tasks meeting person)
DATA_SKILLS=(journal tasks meeting person)

usage() {
    echo "Usage: $0 [--uninstall]"
    echo ""
    echo "Install:   $0"
    echo "Uninstall: $0 --uninstall"
}

install() {
    echo "Installing personal-assistant..."
    echo ""

    # Create skills directory if needed
    mkdir -p "$SKILLS_DIR"

    # Symlink each skill
    for skill in "${SKILLS[@]}"; do
        target="$SKILLS_DIR/$skill"
        source="$REPO_DIR/skills/$skill"

        if [ -L "$target" ]; then
            existing=$(readlink "$target")
            if [ "$existing" = "$source" ]; then
                echo "  [skip] $skill — already linked"
            else
                echo "  [warn] $skill — symlink exists pointing to $existing, skipping"
            fi
        elif [ -e "$target" ]; then
            echo "  [warn] $skill — $target already exists (not a symlink), skipping"
        else
            ln -s "$source" "$target"
            echo "  [ok]   $skill — linked"
        fi
    done

    echo ""

    # Create data directories
    for skill in "${DATA_SKILLS[@]}"; do
        dir="$DATA_ROOT/$skill"
        if [ -d "$dir" ]; then
            echo "  [skip] data/$skill — already exists"
        else
            mkdir -p "$dir"
            echo "  [ok]   data/$skill — created"
        fi
    done

    echo ""
    echo "Done! Skills installed to $SKILLS_DIR"
    echo "Data directories at $DATA_ROOT"
}

uninstall() {
    echo "Uninstalling personal-assistant..."
    echo ""

    for skill in "${SKILLS[@]}"; do
        target="$SKILLS_DIR/$skill"
        if [ -L "$target" ]; then
            rm "$target"
            echo "  [ok]   $skill — symlink removed"
        elif [ -e "$target" ]; then
            echo "  [warn] $skill — $target is not a symlink, skipping"
        else
            echo "  [skip] $skill — not found"
        fi
    done

    echo ""
    echo "Done! Symlinks removed. Data in $DATA_ROOT was NOT touched."
}

case "${1:-}" in
    --uninstall)
        uninstall
        ;;
    --help|-h)
        usage
        ;;
    "")
        install
        ;;
    *)
        echo "Unknown option: $1"
        usage
        exit 1
        ;;
esac
