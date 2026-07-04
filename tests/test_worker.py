from harness import worker as W
from harness import models
from harness.metrics import RunMetrics
from claude_agent_sdk import ToolUseBlock


def test_build_options_solo():
    o = W.build_options(models.HAIKU, None, "/tmp/wd", max_turns=42)
    assert o.model == "haiku"
    assert o.cwd == "/tmp/wd"
    assert o.permission_mode == "bypassPermissions"
    assert o.max_turns == 42
    assert "Bash" in o.allowed_tools
    assert "Agent" not in o.allowed_tools
    assert not o.agents  # None 또는 빈 dict
    # 호스트 스킬/전역 CLAUDE.md 격리 + 기획 스킬·위임 차단
    assert o.setting_sources == []
    assert "Skill" in o.disallowed_tools
    assert "Agent" in o.disallowed_tools  # solo는 위임 금지


def test_build_options_advisor_arm():
    o = W.build_options(models.SONNET, models.FABLE, "/tmp/wd")
    assert o.model == "sonnet"
    assert "Agent" in o.allowed_tools
    assert o.agents["advisor"].model == "fable"
    assert o.agents["advisor"].tools == []
    assert o.fallback_model is None  # sonnet worker는 fallback 불필요
    assert o.setting_sources == []
    assert "Skill" in o.disallowed_tools
    assert "Agent" not in o.disallowed_tools  # advisor arm은 위임 허용


def test_build_options_fable_worker_sets_fallback():
    o = W.build_options(models.FABLE, None, "/tmp/wd")
    assert o.model == "fable"
    assert o.fallback_model == "opus"  # Fable refusal 대비


def test_is_advisor_call():
    yes = ToolUseBlock(id="t1", name="Agent", input={"subagent_type": "advisor"})
    other = ToolUseBlock(id="t2", name="Agent", input={"subagent_type": "worker"})
    bash = ToolUseBlock(id="t3", name="Bash", input={"command": "ls"})
    assert W.is_advisor_call(yes)
    assert not W.is_advisor_call(other)
    assert not W.is_advisor_call(bash)


class FakeResult:
    model_usage = {
        "claude-haiku-4-5-20251001": {
            "inputTokens": 100, "outputTokens": 50,
            "cacheReadInputTokens": 0, "cacheCreationInputTokens": 200,
        }
    }
    num_turns = 7
    total_cost_usd = 0.12
    is_error = False


def test_record_result_maps_model_usage():
    m = RunMetrics(arm="haiku-solo")
    W.record_result(m, FakeResult())
    assert m.worker_turns == 7
    assert abs(m.sdk_cost_usd - 0.12) < 1e-9
    assert m.by_model["claude-haiku-4-5"]["input_tokens"] == 100
    assert m.by_model["claude-haiku-4-5"]["output_tokens"] == 50
    assert m.total_cost > 0


def test_record_result_error_records_refusal():
    class Err(FakeResult):
        is_error = True
        subtype = "error_max_turns"

    m = RunMetrics(arm="fable-solo")
    W.record_result(m, Err())
    assert m.refusals == ["error_max_turns"]
