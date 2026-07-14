# recap

A Claude Code skill that loads a past session's full transcript into the current conversation, so the agent regains the memory of work it did days ago, in any project.

## What it does

Claude Code writes every session to an append-only JSONL transcript under `~/.claude/projects/<cwd-encoded>/<uuid>.jsonl`. The built-in `/resume` reopens a session where it started. `recap` goes further: it finds a transcript from any project on disk and reads it into the session you are in right now. You point it at a project path and a session name, the agent absorbs the old conversation, gives you a short recap of where it left off, and continues the work with that context loaded.

Typical use: you debugged something last Tuesday in another repo, opened a fresh session today, and want the agent to remember the decisions from that debugging session without you retyping them.

## How it works

A ~200-line Python script (`scripts/recap.py`) does the locating and dumping; the SKILL.md tells the agent how to drive it.

- **Path encoding is mirrored, never guessed.** Claude Code encodes a project cwd into a directory name by replacing each non-alphanumeric character with `-`. The script reimplements that encoding, so you pass a human path (`~/code/my-api`) and it resolves the transcript directory. It also accepts an already-encoded dir or a direct `.jsonl` path.
- **Session names come from metadata lines, never from message text.** Renamed sessions are stored as dedicated `custom-title` and `ai-title` records in the JSONL. An earlier version scraped message text for the rename and hit false positives when a message quoted a system reminder. The script now trusts only the metadata records, with a uuid-prefix fallback.
- **The dump filters noise by design.** It prints user and assistant messages in order, compresses each tool call to one line (`[tool: Bash] npm test`), and drops raw `tool_result` payloads. Token cost stays proportional to the conversation, and skips the megabytes of file contents the old session read. If one specific tool result matters, the agent opens that line of the `.jsonl` directly.
- **The skill forbids delegating the read to a subagent.** A subagent would absorb the transcript and discard it when it returns a summary. The whole point is getting the context into the main session, so the SKILL.md instructs the agent to read the dump itself.
- **Two-step flow with an escape hatch.** `list` shows each session's name, time range, message counts, and first user message so you pick the right one. `dump` prints the chosen session in full. If the path resolves to a single `.jsonl`, the list step is skipped.

## Usage

Install as a plain skill:

```bash
git clone https://github.com/MrIago/recap ~/.claude/skills/recap
```

Then, inside any Claude Code session:

```
/recap                               # list sessions for the current project, pick one
/recap ~/code/other-project          # list sessions from a different project
/recap ~/code/other-project billing  # recover the session named "billing" directly
```

Arguments: first a path (a project cwd, a `~/.claude/projects` subdir, or a `.jsonl` file), then an optional session name (substring, case-insensitive) or uuid prefix. The script can also run standalone:

```bash
python3 scripts/recap.py list ~/code/my-api
python3 scripts/recap.py dump ~/code/my-api "billing bug"
```

## Scope and honest limits

- Recovering memory costs tokens. A long session produces a long dump, and the agent reads all of it. That trade is the feature; if you only need a slice, ask the agent to summarize the dump instead of retaining each line.
- Raw tool output is omitted on purpose. Decisions and reasoning survive; the 400-line test log does not.
- The script depends on Claude Code's current transcript format (`~/.claude/projects`, JSONL, `custom-title` records). A format change upstream would require a script update.
- Local only. It reads files already on your machine and sends nothing anywhere.
