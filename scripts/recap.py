#!/usr/bin/env python3
"""
recap.py — locate and dump Claude Code session transcripts.

Claude Code stores every session as an append-only JSONL file at
  ~/.claude/projects/<cwd-encoded>/<session-uuid>.jsonl
where <cwd-encoded> is the absolute cwd with every non-alphanumeric char
replaced by "-" (so /home/me/proj -> -home-me-proj).

Its STDOUT is the result the model reads.

Usage:
  recap.py list  <path>                 # list sessions for a project cwd (or a
                                        #   ~/.claude/projects dir, or pass a .jsonl)
  recap.py dump  <path> [name]          # dump ONE session in full.
                                        #   <path> = cwd / project-dir / .jsonl file.
                                        #   [name] = session name OR uuid prefix to pick
                                        #            (omit only when path is a single .jsonl)

Notes:
  - "name" matches the label the user gave via session rename (captured in the
    transcript as a system-reminder: 'The user named this session X').
  - dump prints user/assistant text + tool calls (compact) + rename events,
    in order, so the current session can absorb the full memory.
"""
import sys
import os
import re
import json
import glob

PROJECTS = os.path.expanduser("~/.claude/projects")


def encode_cwd(path: str) -> str:
    """Mirror Claude Code's cwd->dirname encoding: non-alphanumeric -> '-'."""
    return re.sub(r"[^a-zA-Z0-9]", "-", path.rstrip("/"))


def resolve_dir(path: str) -> str:
    """Return the ~/.claude/projects/<encoded> dir for a given input path."""
    # already a projects subdir?
    if os.path.isdir(path) and os.path.commonpath([os.path.abspath(path), PROJECTS]) == PROJECTS:
        return os.path.abspath(path)
    # an encoded dir name passed directly
    cand = os.path.join(PROJECTS, os.path.basename(path.rstrip("/")))
    if os.path.isdir(cand):
        return cand
    # a real cwd -> encode it
    enc = encode_cwd(os.path.abspath(os.path.expanduser(path)))
    cand = os.path.join(PROJECTS, enc)
    if os.path.isdir(cand):
        return cand
    return cand  # may not exist; caller reports


def iter_msgs(jsonl_path):
    with open(jsonl_path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def session_meta(jsonl_path):
    """Return dict: uuid, name, first_user, first_ts, last_ts, n_user, n_asst."""
    name = None        # user-given title (custom-title) — authoritative
    ai_title = None    # auto-generated fallback (ai-title)
    first_user = None
    first_ts = None
    last_ts = None
    n_user = n_asst = 0
    for o in iter_msgs(jsonl_path):
        t = o.get("type")
        # dedicated metadata lines carry the real session name — trust these,
        # never scrape message text (quoted reminders cause false positives).
        if t == "custom-title" and o.get("customTitle"):
            name = o["customTitle"].strip()
            continue
        if t == "ai-title" and o.get("aiTitle"):
            ai_title = o["aiTitle"].strip()
            continue
        ts = (o.get("timestamp") or "")[:19]
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        m = o.get("message", {}) or {}
        role = m.get("role")
        text = extract_text(m)
        if text:
            if role == "user":
                n_user += 1
                if first_user is None and "system-reminder" not in text and not text.startswith("Base directory"):
                    first_user = text.strip().replace("\n", " ")[:90]
            elif role == "assistant":
                n_asst += 1
    return {
        "path": jsonl_path,
        "uuid": os.path.splitext(os.path.basename(jsonl_path))[0],
        "name": name or ai_title,
        "first_user": first_user or "(no plain user message)",
        "first_ts": first_ts or "?",
        "last_ts": last_ts or "?",
        "n_user": n_user,
        "n_asst": n_asst,
    }


def extract_text(m: dict) -> str:
    c = m.get("content", "")
    if isinstance(c, list):
        parts = []
        for x in c:
            if not isinstance(x, dict):
                continue
            t = x.get("type")
            if t == "text":
                parts.append(x.get("text", ""))
            elif t == "tool_use":
                name = x.get("name", "tool")
                inp = x.get("input", {})
                desc = inp.get("description") or inp.get("command") or inp.get("file_path") or ""
                parts.append(f"[tool: {name}] {str(desc)[:120]}")
            elif t == "tool_result":
                pass  # skip noisy tool output in dumps
        return "\n".join(p for p in parts if p)
    return c or ""


def cmd_list(path):
    d = resolve_dir(path)
    if not os.path.isdir(d):
        print(f"ERROR: no session dir for '{path}'. Tried: {d}", file=sys.stderr)
        return 1
    files = sorted(glob.glob(os.path.join(d, "*.jsonl")), key=os.path.getmtime, reverse=True)
    if not files:
        print(f"ERROR: no .jsonl sessions in {d}", file=sys.stderr)
        return 1
    print(f"# Sessions in {d}\n")
    for f in files:
        meta = session_meta(f)
        nm = f'"{meta["name"]}"' if meta["name"] else "(unnamed)"
        print(f"- {nm}  [{meta['uuid'][:8]}]")
        print(f"    {meta['first_ts']} → {meta['last_ts']}  | {meta['n_user']}u/{meta['n_asst']}a")
        print(f"    first: {meta['first_user']}")
    return 0


def find_session(path, selector):
    """Resolve a single .jsonl given path + selector (name or uuid prefix)."""
    if path.endswith(".jsonl") and os.path.isfile(path):
        return path
    d = resolve_dir(path)
    files = glob.glob(os.path.join(d, "*.jsonl"))
    if not files:
        return None
    if not selector:
        return files[0] if len(files) == 1 else None
    sel = selector.strip().lower()
    # uuid prefix match
    for f in files:
        if os.path.basename(f).lower().startswith(sel):
            return f
    # name match (substring, case-insensitive)
    matches = [f for f in files if (session_meta(f)["name"] or "").lower().find(sel) >= 0]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"AMBIGUOUS: '{selector}' matched {len(matches)} sessions; refine.", file=sys.stderr)
    return None


def cmd_dump(path, selector=None):
    f = find_session(path, selector)
    if not f:
        print(f"ERROR: could not resolve a single session for path='{path}' name='{selector}'. "
              f"Run: recap.py list '{path}'", file=sys.stderr)
        return 1
    meta = session_meta(f)
    label = '"%s"' % meta["name"] if meta["name"] else meta["uuid"][:8]
    print("# RECAP — session " + label)
    print(f"# file: {f}")
    print(f"# {meta['first_ts']} → {meta['last_ts']}  ({meta['n_user']} user / {meta['n_asst']} assistant)\n")
    for o in iter_msgs(f):
        m = o.get("message", {}) or {}
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = extract_text(m)
        if not text.strip():
            continue
        ts = (o.get("timestamp") or "")[:19]
        print(f"\n===== [{role}] {ts} =====")
        print(text.strip())
    return 0


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    mode, path = sys.argv[1], sys.argv[2]
    selector = sys.argv[3] if len(sys.argv) > 3 else None
    if mode == "list":
        return cmd_list(path)
    if mode == "dump":
        return cmd_dump(path, selector)
    print(f"ERROR: unknown mode '{mode}' (use 'list' or 'dump')", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (ImportError, AttributeError, ValueError):
        pass
    raise SystemExit(main())
