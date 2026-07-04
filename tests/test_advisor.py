from harness.advisor import advisor_agent, ADVISOR_SYSTEM
from harness import models
from claude_agent_sdk import AgentDefinition


def test_advisor_agent_is_fable_subagent_without_tools():
    a = advisor_agent(models.FABLE)
    assert isinstance(a, AgentDefinition)
    assert a.model == "fable"
    assert a.tools == []
    assert a.prompt == ADVISOR_SYSTEM


def test_advisor_system_forbids_tools():
    assert "no tools" in ADVISOR_SYSTEM.lower()
    assert "numbered" in ADVISOR_SYSTEM.lower()
