# personal-assistant

A Claude Code skills package that turns Claude into a personal assistant — journal, backlog, meetings, and people management, all coordinated by an assistant skill.

## Quick Start

1. Clone the repository:
   ```bash
   git clone https://github.com/blizzarac/personal-assistant.git
   cd personal-assistant
   ```

2. Run the install script:
   ```bash
   python3 install.py        # all platforms
   # or
   ./install.sh              # macOS / Linux only
   ```
   This symlinks the skills, creates data directories, and registers [QMD](https://github.com/tobi/qmd) collections for semantic search (if qmd is installed).

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
| **backlog** | Project-based task management with priorities and due dates | "create a task", "open tasks", "task dashboard" |
| **meeting** | Structured meeting notes linked to journal and people | "meeting with Alice about X", "what meetings did I have?" |
| **person** | People directory with relationships and birthdays | "add person", "birthdays in March", "who is Jane?" |

## How It Works

- **Reads:** The assistant uses [QMD](https://github.com/tobi/qmd) for semantic search across all skills, plus CLIs for structured queries
- **Writes:** The assistant delegates to individual skills via Claude Code's Skill tool for structured creation
- **Data:** Each skill stores markdown files in its own directory

## Tutorial

After installing, open Claude Code in any directory. The skills activate automatically based on what you say.

### Journal

Write about your day — Claude asks follow-up questions one at a time, then creates a structured markdown entry.

```
You: Journal entry — had a productive morning, went for a run, then worked on the API refactor

Claude: Nice! How did the run go?

You: Great, did 5k in 25 minutes

Claude: And how's the API refactor coming along?

You: Almost done, just need to update the tests

Claude: [Creates 2026/2026-02-28-Saturday-Journal.md with structured content]
```

Query past entries with natural language:

```
You: What did I do last week?
You: When did I last go running?
You: Summarize January
```

### Backlog

Create and manage tasks organized by project, with priorities and due dates.

```
You: Create a task to update the API documentation, due next Friday, high priority, project Backend

Claude: [Creates Backend/Update the API documentation.md with frontmatter]
```

```
You: What are my open tasks?
You: Task dashboard
You: Mark the API documentation task as done
You: What tasks are due this week?
```

### Meetings

Describe a meeting and Claude structures it into notes with topics, decisions, and action items. It also links attendees to the people directory and creates a journal entry for the day.

```
You: I had a meeting with Alice and Bob about the Q2 roadmap. We decided to
     prioritize the mobile app. Alice will create the project plan by Friday.
     Bob is handling the infrastructure review.

Claude: [Creates 2026/Q2 Roadmap Planning (2026-02-28).md]
        [Links [[Alice]] and [[Bob]] as attendees]
        [Creates/updates today's journal entry with meeting summary]
```

```
You: What meetings did I have with Alice?
You: Meetings about the roadmap
You: Summarize meetings from February
```

### People

Build a directory of people with relationships, birthdays, and how you met.

```
You: Sarah Chen, met her at the React conference in March. She works at Stripe.

Claude: Anything else? (birthday, tags, notes)

You: Birthday is July 15

Claude: [Creates Sarah Chen.md with frontmatter and notes]
```

```
You: Who is Sarah Chen?
You: Birthdays in March
You: Who did I meet at conferences?
You: Update Sarah — last met today
```

### Cross-Skill Queries

The assistant skill coordinates across all skills when your question spans multiple domains.

```
You: Catch me up on this week
Claude: [Queries journal, meetings, and backlog in parallel, presents a timeline]

You: What's going on with Alice?
Claude: [Searches person directory, meetings with Alice, backlog mentioning Alice]

You: I met Alice yesterday, we discussed the migration project and she'll
     send the proposal by Friday
Claude: I'll do the following:
        1. Meeting: Create meeting notes for the migration discussion
        2. Backlog: Create a task for Alice's proposal, due Friday
        Does that look right?
```

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
