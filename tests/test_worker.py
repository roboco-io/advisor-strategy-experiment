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


class StopDetails:
    def __init__(self, category):
        self.category = category


class Resp:
    def __init__(self, content, stop, stop_details=None):
        self.content = content; self.stop_reason = stop; self.usage = Usage()
        self.stop_details = stop_details


class ScriptedMessages:
    """정해진 순서로 응답을 내주는 페이크."""
    def __init__(self, script):
        self.script = list(script); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class Beta:
    def __init__(self, script):
        self.messages = ScriptedMessages(script)


class Client:
    def __init__(self, script, beta_script=None):
        self.messages = ScriptedMessages(script)
        self.beta = Beta(beta_script if beta_script is not None else [])


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


def test_max_tokens_does_not_end_arm(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    script = [
        Resp([TX("partial")], "max_tokens"),
        Resp([TX("done")], "end_turn"),
    ]
    m = RunMetrics(arm="haiku-solo")
    client = Client(script)
    final = run_worker(client, models.HAIKU, sb, m, spec="build it")
    assert m.worker_turns == 2
    assert "done" in final


def test_fable_solo_routes_through_beta_and_records_refusal(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    beta_script = [Resp([], "refusal", stop_details=StopDetails("cyber"))]
    m = RunMetrics(arm="fable-solo")
    client = Client(script=[], beta_script=beta_script)
    final = run_worker(client, models.FABLE, sb, m, spec="build it")
    assert m.refusals == ["cyber"]
    assert final == ""
    assert len(client.beta.messages.calls) == 1
    assert client.beta.messages.calls[0].get("betas") == ["server-side-fallback-2026-06-01"]
    assert len(client.messages.calls) == 0
