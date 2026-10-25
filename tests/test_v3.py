"""Assert-based checks for the v3 parsers. Run: python tests/test_v3.py"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis.actions import chat_events
from jarvis.history import NO_FOLDER, parse_usage, search_lines


def line(**rec):
    return json.dumps(rec, ensure_ascii=False)


def assistant(msg_id, model="claude-opus-5-5", ts="2026-10-24T10:00:00Z", **usage):
    return line(type="assistant", timestamp=ts, cwd="C:\\dev\\Jarvis",
                message={"id": msg_id, "model": model, "usage": usage, "content": []})


def test_usage():
    u = dict(input_tokens=2, output_tokens=10, cache_read_input_tokens=100, cache_creation_input_tokens=50)
    lines = [
        assistant("m1", **u),
        assistant("m1", **u),  # same message, second content block: counted once
        assistant("m2", model="claude-haiku-5-5", **u),
        assistant("m3", model="<synthetic>", **u),  # error placeholder, not a real API call
        line(type="user", message={"content": "usage"}),
        "not json \"usage\"",
    ]
    out = parse_usage(lines, "C--dev-Jarvis", set())
    day = next(iter(out))[0]
    assert out == {(day, "Jarvis", "claude-opus-5-5"): [2, 10, 100, 50],
                   (day, "Jarvis", "claude-haiku-5-5"): [2, 10, 100, 50]}, out
    # Already-seen ids (from an earlier incremental read) are skipped.
    assert parse_usage([assistant("m1", **u)], "x", {"m1"}) == {}
    # Scratch sessions are grouped together.
    scratch = parse_usage([assistant("m9", **u)], "C--x-scratch-workspaces-1", set())
    assert next(iter(scratch))[1] == NO_FOLDER


def test_search():
    lines = [
        line(type="user", message={"content": "<system-reminder>Bonjour secret</system-reminder>Corrige le bug"}),
        line(type="assistant", message={"content": [{"type": "text", "text": "J'ai corrigé le BUG \"login\"."},
                                                    {"type": "tool_use", "name": "Bug"}]}),
        line(type="user", isSidechain=True, message={"content": "bug dans un sous-agent"}),
        line(type="user", message={"content": "<command-name>/bug</command-name>"}),
    ]
    hits = list(search_lines(lines, "bug"))
    assert [r["type"] for r, _ in hits] == ["user", "assistant"], hits
    assert hits[0][1] == "Corrige le bug"
    assert list(search_lines(lines, "secret")) == []  # injected reminders are not searched
    assert len(list(search_lines(lines, 'bug "login"'))) == 1  # quotes are escaped inside JSON lines
    assert len(list(search_lines(lines, "corrigé"))) == 1


def test_chat_events():
    state = {}
    ev = lambda **r: chat_events(line(**r), state)
    assert ev(type="system", subtype="init", session_id="abc") == [{"session": "abc"}]
    delta = {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Sal"}}
    assert ev(type="stream_event", event=delta) == [{"text": "Sal"}]
    # The full message repeats streamed text: only its tool calls come through.
    full = {"content": [{"type": "text", "text": "Salut"}, {"type": "tool_use", "name": "Read"}]}
    assert ev(type="assistant", message=full) == [{"tool": "Read"}]
    # A message that was never streamed (e.g. "Not logged in") shows its text.
    assert ev(type="assistant", message={"content": [{"type": "text", "text": "Not logged in"}]}) == [{"text": "Not logged in"}]
    assert ev(type="result", session_id="abc", is_error=True, result="boom", total_cost_usd=0) == \
        [{"done": True, "session": "abc", "cost": 0, "error": "boom"}]
    assert chat_events("Error: bad flag\n", state) == [{"error": "Error: bad flag"}]


if __name__ == "__main__":
    test_usage()
    test_search()
    test_chat_events()
    print("ok")
