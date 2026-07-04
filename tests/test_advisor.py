from harness.advisor import Advisor, CONSULT_ADVISOR_TOOL
from harness.metrics import RunMetrics


class FakeBlock:
    type = "text"
    text = "1. Add JWT auth\n2. Create /api/users"


class FakeUsage:
    input_tokens = 100
    output_tokens = 30
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FakeResp:
    stop_reason = "end_turn"
    content = [FakeBlock()]
    usage = FakeUsage()


class FakeMessages:
    def __init__(self, resp):
        self._resp = resp
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._resp


class FakeClient:
    def __init__(self, resp):
        self.beta = type("B", (), {"messages": FakeMessages(resp)})()


def test_consult_returns_advice_and_records():
    m = RunMetrics(arm="haiku+fable")
    client = FakeClient(FakeResp())
    adv = Advisor(client, m)
    out = adv.consult("How to start?", context="empty repo")
    assert "JWT" in out
    assert m.advisor_calls == 1
    assert m.by_model["claude-fable-5"]["calls"] == 1
    # fallback 파라미터가 요청에 포함됐는지
    kw = client.beta.messages.last_kwargs
    assert kw["model"] == "claude-fable-5"
    assert kw.get("fallbacks") == [{"model": "claude-opus-4-8"}]
    assert "thinking" not in kw


def test_consult_handles_refusal():
    class Refused(FakeResp):
        stop_reason = "refusal"
        content = []
        stop_details = type("S", (), {"category": "cyber"})()

    m = RunMetrics(arm="haiku+fable")
    adv = Advisor(FakeClient(Refused()), m)
    out = adv.consult("q")
    assert "declined" in out.lower()
    assert m.refusals == ["cyber"]


def test_consult_attributes_usage_to_fallback_served_model():
    class FallbackServed(FakeResp):
        model = "claude-opus-4-8"

    m = RunMetrics(arm="haiku+fable")
    adv = Advisor(FakeClient(FallbackServed()), m)
    adv.consult("How to start?", context="empty repo")
    assert m.by_model["claude-opus-4-8"]["calls"] == 1
    assert "claude-fable-5" not in m.by_model


def test_tool_def():
    assert CONSULT_ADVISOR_TOOL["name"] == "consult_advisor"
    assert "question" in CONSULT_ADVISOR_TOOL["input_schema"]["properties"]
