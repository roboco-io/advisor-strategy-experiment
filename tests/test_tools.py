from harness import tools


class Block:
    def __init__(self, name, inp, id="t1"):
        self.name, self.input, self.id = name, inp, id


def test_bash_runs_in_workdir(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    out = sb.run_bash({"command": "echo hi > f.txt && cat f.txt"})
    assert "hi" in out
    assert (tmp_path / "f.txt").read_text().strip() == "hi"


def test_editor_create_and_path_traversal_blocked(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    ok = sb.edit({"command": "create", "path": "app.js", "file_text": "x=1"})
    assert (tmp_path / "app.js").exists()
    res = sb.edit({"command": "create", "path": "../evil.js", "file_text": "bad"})
    assert "error" in res.lower() or "denied" in res.lower()


def test_bash_reaps_background_process(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    sb.run_bash({"command": "sleep 30 & echo $! > pid.txt"})
    pid = int((tmp_path / "pid.txt").read_text().strip())
    import time, os
    time.sleep(0.5)
    # the backgrounded process must have been killed
    alive = True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        alive = False
    assert not alive, f"orphan pid {pid} survived"


def test_handle_tool_use_dispatch(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    r = tools.handle_tool_use(Block("bash", {"command": "echo ok"}), sb)
    assert r["type"] == "tool_result"
    assert r["tool_use_id"] == "t1"
    assert not r.get("is_error")
    bad = tools.handle_tool_use(Block("unknown", {}), sb)
    assert bad["is_error"]
