# personal-assistant

A Claude Code skills package that turns Claude into a personal assistant — journal, tasks, meetings, and people management, all coordinated by an assistant skill.

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/personal-assistant.git
   cd personal-assistant
   ```

2. Run the install script:
   ```bash
   python3 install.py        # all platforms
   # or
   ./install.sh              # macOS / Linux only
   ```

3. Start using it in Claude Code:
   - "Journal entry — had a great day hiking"
   - "Create a task to review the proposal by Friday"
   - "I had a meeting with Alice about the migration"
   - "What happened last week?"

## Skills

| Skill | Description | Example Triggers |
|-------|-------------|-----------------|
| **assistant** | Coordinates across skills for cross-cutting queries | "catch me up", "what happened last week?", "summary of today" |
| **journal** | Daily entries and reflections | "journal entry", "what did I do last week?" |
| **tasks** | Project-based task management with priorities and due dates | "create a task", "open tasks", "task dashboard" |
| **meeting** | Structured meeting notes linked to journal and people | "meeting with Alice about X", "what meetings did I have?" |
| **person** | People directory with relationships and birthdays | "add person", "birthdays in March", "who is Jane?" |

## How It Works

- **Reads:** The assistant queries sub-skill CLIs in parallel for fast lookups
- **Writes:** The assistant delegates to individual skills via Claude Code's Skill tool for structured creation
- **Data:** Each skill stores markdown files in its own directory

## Customizing Data Directories

Each skill has a `config.yaml` in its skill directory. Edit `data_dir` to change where data is stored:

```yaml
# ~/.claude/skills/journal/config.yaml
data_dir: ~/my-custom-path/journal
```

Default location: `~/.local/share/assistant/<skill>/`

## Adding Your Own Skills

To add a new skill to the assistant's registry:

1. Create your skill in `~/.claude/skills/<skill-name>/` with a `skill.md` and optional CLI
2. Add a row to the Skill Registry table in `~/.claude/skills/assistant/skill.md`
3. Add query patterns to the Request Type mapping table

Your CLI should follow the convention: `<skill-name>_cli.py` with `refresh`, `query`, and `read` commands that output JSON.

## Uninstalling

```bash
python3 install.py --uninstall      # all platforms
# or
./install.sh --uninstall            # macOS / Linux only
```

This removes symlinks only. Your data in `~/.local/share/assistant/` is never deleted.

**Windows note:** Creating symlinks requires Developer Mode enabled (Settings > Update & Security > For Developers) or running as Administrator.

## License

MIT
