"""Token usage and full-text search over the session logs in ~/.claude/projects (v3).

Read-only. Only server.py calls these, after the same checks as the actions.
"""

import json
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .inventory import CLAUDE_DIR, REMINDER_RE, SCRATCH_MARKER

PROJECTS = CLAUDE_DIR / "projects"
NO_FOLDER = "(sans dossier)"


def _project_name(rec, folder):
    if SCRATCH_MARKER in folder:
        return NO_FOLDER
    return Path(rec["cwd"]).name if rec.get("cwd") else folder


def _day(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date().isoformat()


def parse_usage(lines, folder, seen):
    """{(day, project, model): [input, output, cache_read, cache_creation]} for these lines.

    One API message is logged once per content block, all with the same usage:
    `seen` holds the message ids already counted.
    """
    out = {}
    for line in lines:
        if '"usage"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get("message") if rec.get("type") == "assistant" else None
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not usage or not rec.get("timestamp") or msg.get("model") == "<synthetic>":
            continue
        if msg.get("id") in seen:
            continue
        seen.add(msg.get("id"))
        key = (_day(rec["timestamp"]), _project_name(rec, folder), msg.get("model") or "?")
        tot = out.setdefault(key, [0, 0, 0, 0])
        for i, f in enumerate(("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")):
            tot[i] += usage.get(f) or 0
    return out


# path -> {"offset": bytes already read, "seen": message ids, "totals": parse_usage result}
_cache = {}
_lock = threading.Lock()


def _read_new(path, entry):
    """Parse only what was appended since last time (session logs only grow)."""
    size = path.stat().st_size
    if size < entry["offset"]:
        entry.update(offset=0, seen=set(), totals={})
    with open(path, "rb") as f:
        f.seek(entry["offset"])
        chunk = f.read(size - entry["offset"])
    end = chunk.rfind(b"\n") + 1  # a line still being written is read next time
    lines = chunk[:end].decode("utf-8", errors="replace").splitlines()
    entry["offset"] += end
    folder = path.relative_to(PROJECTS).parts[0]
    for key, tot in parse_usage(lines, folder, entry["seen"]).items():
        acc = entry["totals"].setdefault(key, [0, 0, 0, 0])
        for i, v in enumerate(tot):
            acc[i] += v


def usage(days=14):
    """Tokens per day, project and model over the last `days` days, subagents included."""
    # shortcut: the cache lives in memory, so the first call after a restart reads every log (a few seconds).
    first = (date.today() - timedelta(days=days - 1)).isoformat()
    cutoff = datetime.fromisoformat(first).timestamp()
    rows = {}
    with _lock:
        for path in PROJECTS.rglob("*.jsonl"):
            if path.stat().st_mtime < cutoff:
                continue  # untouched since before the window: nothing to count in it
            entry = _cache.setdefault(str(path), {"offset": 0, "seen": set(), "totals": {}})
            _read_new(path, entry)
            for key, tot in entry["totals"].items():
                if key[0] >= first:
                    acc = rows.setdefault(key, [0, 0, 0, 0])
                    for i, v in enumerate(tot):
                        acc[i] += v
    return {
        "days": [(date.today() - timedelta(days=d)).isoformat() for d in range(days - 1, -1, -1)],
        "rows": [{"day": d, "project": p, "model": m, "input": t[0], "output": t[1], "cacheRead": t[2], "cacheCreation": t[3]}
                 for (d, p, m), t in sorted(rows.items())],
    }


def _texts(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return [content]
    return [c.get("text", "") for c in content or [] if isinstance(c, dict) and c.get("type") == "text"]


def search_lines(lines, needle):
    """(record, text) for each prompt or reply whose text contains `needle` (lowercase)."""
    raw = json.dumps(needle, ensure_ascii=False)[1:-1]  # how the needle looks inside a JSON line
    for line in lines:
        if raw not in line.lower():
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("type") not in ("user", "assistant") or rec.get("isSidechain"):
            continue
        for t in _texts(rec):
            t = REMINDER_RE.sub("", t).strip()
            if needle in t.lower() and not t.startswith("<"):
                yield rec, t


def _snippet(text, needle, width=160):
    i = text.lower().find(needle)
    start = max(0, i - width // 3)
    s = " ".join(text[start:start + width].split())
    return ("…" if start else "") + s + ("…" if start + width < len(text) else "")


def search(query, limit=50):
    """Prompts and replies of every resumable session containing `query`, newest sessions first."""
    needle = query.strip().lower()
    if len(needle) < 2:
        return []
    files = sorted((f for d in PROJECTS.iterdir() if d.is_dir() and SCRATCH_MARKER not in d.name
                    for f in d.glob("*.jsonl")), key=lambda f: f.stat().st_mtime, reverse=True)
    out = []
    for f in files:
        # shortcut: reads each log in full on every search (~1 s per 200 MB); add an index if it gets slow.
        with open(f, encoding="utf-8", errors="replace") as fh:
            hits = [{"project": Path(rec.get("cwd") or "").name or f.parent.name, "path": rec.get("cwd") or "",
                     "session": f.stem, "at": rec.get("timestamp"), "role": rec["type"],
                     "snippet": _snippet(text, needle)} for rec, text in search_lines(fh, needle)]
        out += sorted(hits, key=lambda h: h["at"] or "", reverse=True)
        if len(out) >= limit:
            break
    return out[:limit]


# --- Live activity (Wisp's moods) ---------------------------------------------

def session_state(lines, age):
    """'working', 'waiting', 'done' or 'idle' for one session log, from its last turn
    and `age`, the seconds since the log was last written."""
    last = None
    for l in lines:
        try:
            rec = json.loads(l)
        except ValueError:
            continue
        if rec.get("type") in ("user", "assistant") and not rec.get("isSidechain"):
            last = rec
    if not last:
        return "idle"
    stop = (last.get("message") or {}).get("stop_reason")
    if last["type"] == "assistant" and stop in ("end_turn", "stop_sequence"):
        return "done" if age < 120 else "idle"
    if last["type"] == "assistant" and stop == "tool_use" and age >= 30:
        # shortcut: a tool call that sits unanswered is read as a permission prompt; a long
        # command (build, tests) looks the same. Upgrade if Claude Code ever logs the prompt itself.
        return "waiting" if age < 600 else "idle"
    return "working" if age < 120 else "idle"


def activity():
    """Live state of the sessions written in the last 10 minutes, plus the overall mood."""
    now = time.time()
    out = []
    for f in PROJECTS.glob("*/*.jsonl"):
        age = now - f.stat().st_mtime
        if age > 600:
            continue
        with open(f, "rb") as fh:  # the last turn is in the tail (1 MB: request blobs can be big)
            start = fh.seek(max(0, fh.seek(0, 2) - (1 << 20)))
            lines = fh.read().decode("utf-8", "replace").splitlines()[1 if start else 0:]  # drop the cut line
        out.append({"session": f.stem, "state": session_state(lines, age), "age": round(age)})
    states = {s["state"] for s in out}
    mood = next((m for st, m in (("waiting", "wow"), ("working", "think"), ("done", "gg")) if st in states),
                "idle" if out else "sleep")
    return {"mood": mood, "sessions": out}
