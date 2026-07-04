"""Fable advisor를 Agent SDK 서브에이전트로 정의."""
from __future__ import annotations
from claude_agent_sdk import AgentDefinition
from harness import models

ADVISOR_SYSTEM = (
    "You are an advisor to a coding agent building a RealWorld (Conduit) backend API "
    "in Node.js + Express + SQLite. You give strategy, not implementations. "
    "You have no tools: you cannot edit files or run commands. When consulted, respond "
    "in 100 words or fewer with a numbered list of concrete next steps."
)


def advisor_agent(model: str = models.FABLE) -> AgentDefinition:
    """worker가 위임 호출할 advisor 서브에이전트 정의(도구 없이 조언만)."""
    return AgentDefinition(
        description=(
            "Consult for strategic guidance before starting real work, when stuck, "
            "or to verify completion. Returns a short numbered list of steps."
        ),
        prompt=ADVISOR_SYSTEM,
        tools=[],
        model=models.ALIAS.get(model, model),
    )
