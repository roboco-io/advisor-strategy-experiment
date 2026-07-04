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
    "Build a RealWorld (Conduit) backend API in Node.js + Express + SQLite, NOW. "
    "Your working directory is: {workdir}\n"
    "ALL files and commands MUST be inside that directory. Use relative paths (or that exact "
    "absolute path). Do NOT use /tmp, your home directory, or any path outside it, and do NOT "
    "`cd` elsewhere — grade tooling runs `npm start` from that directory.\n"
    "Do not write a plan or ask questions — write the actual source files and run the server "
    "yourself using the Bash/Write/Edit tools. Create package.json with a `start` script, "
    "install dependencies (`npm install`), implement the endpoints, and start the server "
    "listening on `process.env.PORT || 3000`. {advisor_hint}Keep working until "
    "`curl -s http://localhost:${{PORT:-3000}}/api/tags` returns a JSON body — only then stop. "
    "Do NOT stop after merely planning or scaffolding.\n\n=== RealWorld API spec ===\n{spec}"
)

ADVISOR_HINT = (
    "Before starting real work, when stuck, and to verify completion, delegate to the "
    "'advisor' subagent for strategy (it returns numbered steps). "
)


def build_options(worker_model, advisor_model, workdir, max_turns: int = 60) -> ClaudeAgentOptions:
    """arm의 worker/advisor 조합으로 ClaudeAgentOptions를 구성(순수 함수)."""
    tools = list(BASE_TOOLS)
    # 호스트의 skills/plugins/전역 CLAUDE.md를 상속하지 않도록 격리(setting_sources=[]).
    # 기획 스킬로 이탈하지 않게 Skill/SlashCommand 차단.
    disallowed = ["Skill"]
    kwargs = {
        "cwd": str(workdir),
        "model": models.ALIAS.get(worker_model, worker_model),
        "permission_mode": "bypassPermissions",
        "max_turns": max_turns,
        "setting_sources": [],
    }
    if advisor_model is not None:
        tools.append("Agent")
        kwargs["agents"] = {"advisor": advisor_agent(advisor_model)}
    else:
        # solo arm은 위임 자체를 막아 순수 단독 성능을 측정.
        disallowed += ["Task", "Agent"]
    # Fable worker는 안전 분류기 refusal 대비 opus fallback을 건다(spec §3).
    # (advisor 서브에이전트에는 SDK가 per-agent fallback을 노출하지 않음 — 한계.)
    if worker_model == models.FABLE:
        kwargs["fallback_model"] = models.ALIAS[models.OPUS]
    kwargs["allowed_tools"] = tools
    kwargs["disallowed_tools"] = disallowed
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
    prompt = WORKER_INSTRUCTIONS.format(advisor_hint=hint, spec=spec, workdir=str(workdir))

    advisor_calls = 0
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if is_advisor_call(block):
                    advisor_calls += 1
        elif isinstance(message, ResultMessage):
            record_result(metrics, message)
    metrics.advisor_calls = advisor_calls
