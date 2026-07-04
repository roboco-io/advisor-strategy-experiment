from harness.worker import run_worker
from harness import tools as T
from harness.metrics import RunMetrics
from harness import models


class TU:
    def __init__(self, name, inp, id):
        self.type = "tool_use"; self.name = name; self.input = inp; self.id = id


class TX:
    def __init__(self, text):
        self.type = "text"; self.text = text


class Usage:
    input_tokens = 10; output_tokens = 5
    cache_read_input_tokens = 0; cache_creation_input_tokens = 0


class Resp:
    def __init__(self, content, stop):
        self.content = content; self.stop_reason = stop; self.usage = Usage()


class ScriptedMessages:
    """정해진 순서로 응답을 내주는 페이크."""
    def __init__(self, script):
        self.script = list(script); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class Client:
    def __init__(self, script):
        self.messages = ScriptedMessages(script)


def test_worker_uses_bash_then_finishes(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    script = [
        Resp([TU("bash", {"command": "echo built > done.txt"}, "u1")], "tool_use"),
        Resp([TX("done")], "end_turn"),
    ]
    m = RunMetrics(arm="haiku-solo")
    client = Client(script)
    final = run_worker(client, models.HAIKU, sb, m, spec="build it")
    assert "done" in final
    assert (tmp_path / "done.txt").exists()
    assert m.worker_turns == 2
    # Haiku는 effort 미포함; 두 번의 실제 API 호출이 일어났는지 확인
    assert len(client.messages.calls) == 2
    assert all("output_config" not in c for c in client.messages.calls)


def test_sonnet_includes_effort(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    client = Client([Resp([TX("ok")], "end_turn")])
    run_worker(client, models.SONNET, sb, RunMetrics(arm="sonnet-solo"), spec="x")
    assert client.messages.calls[0].get("output_config", {}).get("effort") == "high"


def test_haiku_omits_effort(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    client = Client([Resp([TX("ok")], "end_turn")])
    run_worker(client, models.HAIKU, sb, RunMetrics(arm="haiku-solo"), spec="x")
    assert "output_config" not in client.messages.calls[0]
