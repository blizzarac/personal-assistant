#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"
DATA_ROOT="$HOME/.local/share/assistant"
SKILLS=(assistant journal backlog meeting person)
DATA_SKILLS=(journal backlog meeting person)

# QMD collection names map to data directories
declare -A QMD_COLLECTIONS=(
    [journal]="$DATA_ROOT/journal"
    [backlog]="$DATA_ROOT/backlog"
    [meeting]="$DATA_ROOT/meeting"
    [person]="$DATA_ROOT/person"
)

declare -A QMD_CONTEXTS=(
    [journal]="Daily journal entries and reflections, organized by year"
    [backlog]="Task backlog organized by project folders, with priorities and due dates"
    [meeting]="Meeting notes with attendees, topics, decisions, and action items"
    [person]="People directory with relationships, birthdays, and how we met"
)

usage() {
    echo "Usage: $0 [--uninstall]"
    echo ""
    echo "Install:   $0"
    echo "Uninstall: $0 --uninstall"
}

setup_qmd() {
    if ! command -v qmd &>/dev/null; then
        echo "  [skip] qmd — not installed (install with: npm install -g @tobilu/qmd)"
        return
    fi

    echo "  Setting up QMD collections..."
    local existing
    existing=$(qmd collection list 2>/dev/null || true)

    for name in "${!QMD_COLLECTIONS[@]}"; do
        local path="${QMD_COLLECTIONS[$name]}"
        if echo "$existing" | grep -q "$name"; then
            echo "  [skip] qmd/$name — collection already exists"
        else
            if qmd collection add "$path" --name "$name" 2>/dev/null; then
                echo "  [ok]   qmd/$name — collection added"
            else
                echo "  [warn] qmd/$name — failed to add collection"
            fi
        fi

        # Add context (idempotent)
        local ctx="${QMD_CONTEXTS[$name]}"
        qmd context add "qmd://$name" "$ctx" 2>/dev/null || true
    done

    echo "  Embedding QMD collections..."
    if qmd embed 2>/dev/null; then
        echo "  [ok]   qmd — embedding complete"
    else
        echo "  [warn] qmd — embedding failed (run 'qmd embed' manually)"
    fi
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

    # Set up QMD collections
    setup_qmd

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

    # Remove QMD collections
    if command -v qmd &>/dev/null; then
        echo ""
        for name in "${!QMD_COLLECTIONS[@]}"; do
            if qmd collection remove "$name" 2>/dev/null; then
                echo "  [ok]   qmd/$name — collection removed"
            else
                echo "  [skip] qmd/$name — not found"
            fi
        done
    fi

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
