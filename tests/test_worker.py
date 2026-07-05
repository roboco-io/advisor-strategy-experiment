from harness import worker as W
from harness import models
from harness.metrics import RunMetrics


def test_build_worker_options_solo():
    o = W.build_worker_options(models.HAIKU, "/tmp/wd", max_turns=40)
    assert o.model == "haiku"
    assert o.cwd == "/tmp/wd"
    assert o.permission_mode == "bypassPermissions"
    assert o.setting_sources == []  # 호스트 스킬/CLAUDE.md 격리
    assert {"Bash", "Read", "Write", "Edit", "Glob", "Grep"}.issubset(set(o.allowed_tools))
    assert "Skill" in o.disallowed_tools
    assert "Agent" in o.disallowed_tools  # 위임 차단(advisor는 하니스가 주입)
    assert o.fallback_model is None


def test_build_worker_options_fable_fallback():
    o = W.build_worker_options(models.FABLE, "/tmp/wd")
    assert o.model == "fable"
    assert o.fallback_model == "opus"


def test_build_advisor_options():
    o = W.build_advisor_options(models.FABLE)
    assert o.model == "fable"
    assert o.allowed_tools == []
    assert o.system_prompt == W.ADVISOR_SYSTEM
    assert o.setting_sources == []
    assert o.max_turns == 1
    assert o.fallback_model == "opus"


class FakeResult:
    def __init__(self, model_usage, num_turns=5, cost=0.1, is_error=False, subtype="success"):
        self.model_usage = model_usage
        self.num_turns = num_turns
        self.total_cost_usd = cost
        self.is_error = is_error
        self.subtype = subtype


def _mu(model, out=50):
    return {model: {"inputTokens": 100, "outputTokens": out,
                    "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0}}


def test_build_delegator_options():
    o = W.build_delegator_options(models.SONNET, models.OPUS, "/tmp/wd", max_turns=40)
    assert o.model == "sonnet"
    assert o.cwd == "/tmp/wd"
    assert o.permission_mode == "bypassPermissions"
    assert o.setting_sources == []
    assert "Agent" in o.allowed_tools and "Task" in o.allowed_tools  # 서브에이전트 소환 도구
    assert "Skill" in o.disallowed_tools
    assert "worker" in o.agents  # Opus 구현 서브에이전트
    assert o.agents["worker"].model == "opus"
    assert o.agents["worker"].permissionMode == "bypassPermissions"  # 헤드리스 정지 방지
    assert o.fallback_model is None  # Sonnet 플래너는 fallback 없음


def test_build_delegator_options_fable_planner_haiku_executor():
    # Plan-then-Execute: Fable 플래너 + Haiku 실행자
    o = W.build_delegator_options(models.FABLE, models.HAIKU, "/tmp/wd")
    assert o.model == "fable"
    assert o.agents["worker"].model == "haiku"
    assert o.fallback_model == "opus"  # Fable refusal 대비


def test_accumulate_separates_worker_and_advisor():
    m = RunMetrics(arm="haiku+fable")
    W._accumulate(m, FakeResult(_mu("claude-haiku-4-5-20251001"), num_turns=7, cost=0.2), is_worker=True)
    W._accumulate(m, FakeResult(_mu("claude-fable-5"), num_turns=1, cost=0.5), is_worker=False)
    assert m.worker_turns == 7  # advisor 턴은 worker_turns에 미포함
    assert abs(m.sdk_cost_usd - 0.7) < 1e-9
    assert "claude-haiku-4-5" in m.by_model
    assert "claude-fable-5" in m.by_model


def test_accumulate_error_records_refusal():
    m = RunMetrics(arm="fable-solo")
    W._accumulate(m, FakeResult({}, is_error=True, subtype="error_max_turns"), is_worker=True)
    assert m.refusals == ["error_max_turns"]
