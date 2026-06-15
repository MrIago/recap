---
name: recap
description: Recover a past Claude Code session into the CURRENT conversation — read its full transcript so you regain all the memory/context from it. Use when the user runs /recap, asks to resume/recover/restore/import a previous session or conversation, says context was lost, or wants to bring context from another project/session into this one. Works across any project, no /resume needed.
argument-hint: "[path] [session name]"
allowed-tools: Bash, Read
---

# recap — pull a past session's full context into this one

Claude Code stores every session as an append-only JSONL transcript at
`~/.claude/projects/<cwd-encoded>/<uuid>.jsonl` (the cwd has every
non-alphanumeric char replaced by `-`). This skill reads one of those files
**directly into the current conversation** so you recover its entire memory and
can keep working with that context — no `/resume`, works across projects.

Arguments: `$1` = path (a project cwd, a `~/.claude/projects` dir, or a `.jsonl`
file). `$2` = optional session name (the label the user gave via rename) or uuid
prefix.

## Do NOT use a subagent

The whole point is to load the transcript into THIS session's context. Run the
script and read its stdout yourself. A subagent would absorb the context and
throw it away on return — defeating the purpose.

## Flow

### 1. If no session name was given → list and ask

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/recap.py" list "$1"
```

Show the user the sessions (name, time range, message counts, first message) and
ask which one to recover. If `$1` is missing, default to the current project cwd.
If `$1` resolves to exactly one `.jsonl`, skip straight to dump.

### 2. Dump the chosen session in full

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/recap.py" dump "$1" "<name-or-uuid-prefix>"
```

The output is the transcript: user/assistant messages in order, with tool calls
shown compactly and rename events inline. **Read all of it** — that is the
context you are recovering. The script omits noisy raw tool_result output on
purpose; if a specific tool result matters, open the `.jsonl` and read that line.

### 3. Confirm + continue

After reading, give a short recap to the user (what that session was about, where
it left off, key decisions) so they see the memory landed, then continue the work
with that context in hand.

## Notes

- The path encoding (cwd → dir name) and session resolution are handled by the
  script; you just pass the human path.
- If a session was renamed, the script finds it by that name (substring,
  case-insensitive). It also accepts a uuid prefix.
- Long transcripts can be big. That's expected — recovering memory costs tokens.
  If the user only needs a slice, they can pass the name and you can read the dump
  and summarize rather than retain every line.
