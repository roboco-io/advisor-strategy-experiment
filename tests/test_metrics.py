from harness.metrics import RunMetrics
from harness import models


class FakeUsage:
    def __init__(self, i, o, cr=0, cw=0):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_read_input_tokens = cr
        self.cache_creation_input_tokens = cw


def test_add_usage_accumulates_cost():
    m = RunMetrics(arm="haiku-solo")
    m.add_usage(models.HAIKU, FakeUsage(1_000_000, 1_000_000))
    assert abs(m.total_cost - 6.0) < 1e-9
    assert m.by_model[models.HAIKU]["input_tokens"] == 1_000_000


def test_counters_and_serialize(tmp_path):
    m = RunMetrics(arm="haiku+fable")
    m.note_turn()
    m.note_advisor_call()
    m.note_refusal("cyber")
    d = m.to_dict()
    assert d["worker_turns"] == 1
    assert d["advisor_calls"] == 1
    assert d["refusals"] == ["cyber"]
    p = tmp_path / "r.json"
    m.save(str(p))
    assert p.exists()


def test_add_model_usage_normalizes_and_costs():
    m = RunMetrics(arm="x")
    m.add_model_usage({
        "claude-haiku-4-5-20251001": {
            "inputTokens": 1_000_000, "outputTokens": 1_000_000,
            "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
        }
    })
    # 날짜 포함 ID가 단가표 키로 정규화되고 비용이 계산됨
    assert "claude-haiku-4-5" in m.by_model
    assert m.by_model["claude-haiku-4-5"]["output_tokens"] == 1_000_000
    assert abs(m.total_cost - 6.0) < 1e-9
