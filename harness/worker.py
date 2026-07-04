"""Agent SDK 기반 executor. worker가 루프를 소유하고, advisor arm에서는 Fable
서브에이전트에 위임한다. 구독 인증(ANTHROPIC_API_KEY 미설정)으로 실행된다."""
from __future__ import annotations

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    ToolUseBlock,
)
from harness import models
from harness.advisor import advisor_agent

BASE_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]

WORKER_INSTRUCTIONS = (
    "Build a RealWorld (Conduit) backend API in Node.js + Express + SQLite in the current "
    "working directory. Use the file and bash tools to write code and run it. Goal: a "
    "running server (`npm start`, listening on the PORT env var, default 3000) that "
    "satisfies the spec below. {advisor_hint}When the server is complete and you have "
    "smoke-tested it yourself, stop.\n\n=== RealWorld API spec ===\n{spec}"
)

ADVISOR_HINT = (
    "Before starting real work, when stuck, and to verify completion, delegate to the "
    "'advisor' subagent for strategy (it returns numbered steps). "
)


def build_options(worker_model, advisor_model, workdir, max_turns: int = 60) -> ClaudeAgentOptions:
    """arm의 worker/advisor 조합으로 ClaudeAgentOptions를 구성(순수 함수)."""
    tools = list(BASE_TOOLS)
    kwargs = {
        "cwd": str(workdir),
        "model": models.ALIAS.get(worker_model, worker_model),
        "permission_mode": "bypassPermissions",
        "max_turns": max_turns,
    }
    if advisor_model is not None:
        tools.append("Agent")
        kwargs["agents"] = {"advisor": advisor_agent(advisor_model)}
    # Fable worker는 안전 분류기 refusal 대비 opus fallback을 건다(spec §3).
    # (advisor 서브에이전트에는 SDK가 per-agent fallback을 노출하지 않음 — 한계.)
    if worker_model == models.FABLE:
        kwargs["fallback_model"] = models.ALIAS[models.OPUS]
    kwargs["allowed_tools"] = tools
    return ClaudeAgentOptions(**kwargs)


def is_advisor_call(block) -> bool:
    """assistant 블록이 advisor 서브에이전트 위임 호출인지 판별."""
    return (
        isinstance(block, ToolUseBlock)
        and block.name in ("Task", "Agent")
        and (block.input or {}).get("subagent_type") == "advisor"
    )


def record_result(metrics, result) -> None:
    """ResultMessage에서 모델별 usage·턴수·SDK 추정비용을 metrics에 반영."""
    metrics.add_model_usage(getattr(result, "model_usage", None) or {})
    metrics.worker_turns = getattr(result, "num_turns", 0) or 0
    metrics.sdk_cost_usd = getattr(result, "total_cost_usd", 0.0) or 0.0
    if getattr(result, "is_error", False):
        metrics.note_refusal(getattr(result, "subtype", "error"))


async def run_worker(worker_model, advisor_model, workdir, spec, metrics, max_turns: int = 60) -> None:
    """라이브 executor 루프. arm당 1회 호출. (외부 SDK 의존 — 단위 테스트 제외)"""
    options = build_options(worker_model, advisor_model, workdir, max_turns)
    hint = ADVISOR_HINT if advisor_model is not None else ""
    prompt = WORKER_INSTRUCTIONS.format(advisor_hint=hint, spec=spec)

    advisor_calls = 0
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if is_advisor_call(block):
                    advisor_calls += 1
        elif isinstance(message, ResultMessage):
            record_result(metrics, message)
    metrics.advisor_calls = advisor_calls
