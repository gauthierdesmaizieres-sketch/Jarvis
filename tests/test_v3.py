"""Assert-based checks for the v3 parsers. Run: python tests/test_v3.py"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jarvis import actions, board, inventory, system
from jarvis.actions import chat_events
from jarvis.history import NO_FOLDER, parse_usage, search_lines, session_state


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


def test_rename_link():
    with tempfile.TemporaryDirectory() as tmp:
        actions.NAMES_FILE = Path(tmp) / "names.json"
        actions.NAMES_FILE.write_text("{}", encoding="utf-8")
        actions.collect = lambda: {"projects": [{"name": "App", "links": [{"url": "https://a"}]}]}
        rename = lambda **req: actions.rename_link({"project": "App", "url": "https://a", **req})
        names = lambda: json.loads(actions.NAMES_FILE.read_text(encoding="utf-8"))
        rename(label=" Mon app ")
        assert names() == {"App": {"https://a": "Mon app"}}
        rename(label="")  # back to the project's name
        assert names() == {}
        for bad in (dict(label="x", url="https://autre"), dict(label="x" * 41), dict(label="a\nb")):
            try:
                rename(**bad)
                raise AssertionError(bad)
            except actions.ActionError:
                pass
        assert names() == {}


def test_moved_session():
    with tempfile.TemporaryDirectory() as tmp:
        inventory.CLAUDE_DIR = Path(tmp)
        d = Path(tmp) / "projects" / "C--Users-me-Tama"
        d.mkdir(parents=True)
        cwd = lambda p: json.dumps({"type": "user", "cwd": p}, separators=(",", ":"))  # compact, like Claude Code's logs
        # Started in a scratch folder, then a detour elsewhere, then moved to C:\Users\me\Tama.
        (d / "s.jsonl").write_text("\n".join([cwd("C:\\x\\scratch-workspaces\\1"), cwd("C:\\dev\\Jarvis"),
                                             cwd("C:\\Users\\me\\Tama")]), encoding="utf-8")
        assert inventory._session_cwds() == {"C:\\Users\\me\\Tama"}


def test_session_state():
    turn = lambda stop: line(type="assistant", message={"stop_reason": stop, "content": []})
    prompt = line(type="user", message={"content": "go"})
    assert session_state([prompt], 5) == "working"
    assert session_state([prompt, turn("tool_use")], 5) == "working"
    assert session_state([prompt, turn("tool_use")], 60) == "waiting"  # unanswered tool call: permission prompt
    assert session_state([prompt, turn("end_turn")], 10) == "done"
    assert session_state([prompt, turn("end_turn")], 300) == "idle"
    assert session_state([prompt, turn("end_turn"), line(type="attachment"), "cut {"], 10) == "done"
    assert session_state([], 1) == "idle"


def test_board():
    import os, subprocess
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        repo, plain = home / "repo", home / "plain"
        (repo / "node_modules").mkdir(parents=True)
        plain.mkdir()
        for f, t in ((repo / "a.txt", 1_000_000), (repo / "node_modules" / "x.js", 2_000_000), (plain / "b.txt", 500)):
            f.write_text("x", encoding="utf-8")
            os.utime(f, (t, t))
        assert board.latest_mtime(repo) == 1_000_000  # node_modules is ignored
        git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                        check=True, capture_output=True)
        git("init", "-q", "-b", "main")
        git("add", "a.txt")
        git("commit", "-q", "-m", "premier commit")
        (repo / "new.txt").write_text("x", encoding="utf-8")
        g = board.git_info(repo)
        assert (g["branch"], g["commitMsg"], g["dirty"]) == ("main", "premier commit", 2), g  # new.txt + node_modules/
        assert g["commitDate"][:4].isdigit()
        assert board.git_info(plain) is None
        cfg = home / "projects.json"
        cfg.write_text(json.dumps({"_aide": "x", "D": [{"name": "P", "path": "plain"}, {"name": "R", "path": "repo"},
                                                       {"name": "M", "path": "absent"}]}), encoding="utf-8")
        out = board.board(cfg, home)
        assert [r["name"] for r in out] == ["R", "P", "M"], out  # newest first, missing last
        assert out[2]["exists"] is False and "git" not in out[2]


def test_cpu_percent():
    system._last = None
    assert system.cpu_percent((100, 1000)) is None  # no earlier sample yet
    assert system.cpu_percent((175, 1100)) == 25  # 75 idle out of 100
    assert system.cpu_percent((175, 1100)) is None  # no time passed
    assert 0 <= system.system()["disk"] <= 100


if __name__ == "__main__":
    test_usage()
    test_search()
    test_chat_events()
    test_rename_link()
    test_cpu_percent()
    test_moved_session()
    test_session_state()
    test_board()
    print("ok")
