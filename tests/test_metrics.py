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
