"""하니스가 루프를 소유하는 executor. worker는 ClaudeSDKClient로 코드를 짓고,
advisor arm에서는 하니스가 Fable을 직접 상담해 조언을 worker 세션에 주입한다(상담 강제).
구독 인증(ANTHROPIC_API_KEY 미설정)으로 실행된다."""
from __future__ import annotations

from claude_agent_sdk import (
    query,
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
)
from harness import models
from harness.advisor import ADVISOR_SYSTEM

BASE_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep"]
# worker가 기획 스킬로 이탈하거나 임의 위임하지 않도록 차단(advisor는 하니스가 주입).
WORKER_DISALLOWED = ["Skill", "Task", "Agent"]
MAX_ADVISOR_ROUNDS = 3  # 연구 권장 2-3회 상담

WORKER_INSTRUCTIONS = (
    "Build a RealWorld (Conduit) backend API in Node.js + Express + SQLite, NOW. "
    "Your working directory is: {workdir}\n"
    "ALL files and commands MUST be inside that directory (relative paths, or that exact "
    "absolute path). Do NOT use /tmp, your home directory, or any path outside it, and do "
    "NOT `cd` elsewhere — grade tooling runs `npm start` from that directory.\n"
    "Do not write a plan or ask questions — write the actual source files and run the server "
    "yourself with the Bash/Write/Edit tools. Create package.json with a `start` script, "
    "install dependencies (`npm install`), implement the endpoints, and start the server on "
    "`process.env.PORT || 3000`. Keep working until "
    "`curl -s http://localhost:${{PORT:-3000}}/api/tags` returns a JSON body.\n\n"
    "=== RealWorld API spec ===\n{spec}"
)

WORKER_CONTINUE = (
    "Advisor guidance for your next steps:\n{advice}\n\n"
    "Apply it: fix gaps and keep working until "
    "`curl -s http://localhost:${{PORT:-3000}}/api/tags` returns JSON. If everything already "
    "works, verify with curl and stop."
)


def build_worker_options(worker_model, workdir, max_turns: int = 40) -> ClaudeAgentOptions:
    """worker(executor) 세션 옵션. 호스트 스킬 격리, 위임/스킬 차단."""
    kwargs = {
        "cwd": str(workdir),
        "model": models.ALIAS.get(worker_model, worker_model),
        "permission_mode": "bypassPermissions",
        "max_turns": max_turns,
        "setting_sources": [],
        "allowed_tools": list(BASE_TOOLS),
        "disallowed_tools": list(WORKER_DISALLOWED),
    }
    if worker_model == models.FABLE:
        kwargs["fallback_model"] = models.ALIAS[models.OPUS]
    return ClaudeAgentOptions(**kwargs)


def build_advisor_options(advisor_model) -> ClaudeAgentOptions:
    """advisor(Fable) 상담용 one-shot 옵션. 도구 없음, 조언만."""
    kwargs = {
        "model": models.ALIAS.get(advisor_model, advisor_model),
        "system_prompt": ADVISOR_SYSTEM,
        "setting_sources": [],
        "allowed_tools": [],
        "disallowed_tools": list(WORKER_DISALLOWED),
        "max_turns": 1,
    }
    if advisor_model == models.FABLE:
        kwargs["fallback_model"] = models.ALIAS[models.OPUS]
    return ClaudeAgentOptions(**kwargs)


def _accumulate(metrics, result, is_worker: bool) -> None:
    """ResultMessage의 모델별 usage·비용·턴수를 metrics에 누적."""
    metrics.add_model_usage(getattr(result, "model_usage", None) or {})
    metrics.sdk_cost_usd += getattr(result, "total_cost_usd", 0.0) or 0.0
    if is_worker:
        metrics.worker_turns += getattr(result, "num_turns", 0) or 0
    if getattr(result, "is_error", False):
        metrics.note_refusal(getattr(result, "subtype", "error"))


async def consult_advisor(advisor_model, question: str, context: str, metrics) -> str:
    """Fable을 직접 상담해 조언 텍스트를 반환(상담 강제, 사용량 계측)."""
    opts = build_advisor_options(advisor_model)
    prompt = f"Question: {question}\n\nContext:\n{context}"
    advice = ""
    async for m in query(prompt=prompt, options=opts):
        if isinstance(m, AssistantMessage):
            t = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
            if t.strip():
                advice = t
        elif isinstance(m, ResultMessage):
            _accumulate(metrics, m, is_worker=False)
            advice = getattr(m, "result", None) or advice
    metrics.note_advisor_call()
    return advice or "(no advice)"


async def _drain_turn(worker, metrics) -> str:
    """worker의 한 턴을 끝까지 소비하고 마지막 텍스트를 반환."""
    last_text = ""
    async for m in worker.receive_response():
        if isinstance(m, AssistantMessage):
            t = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
            if t.strip():
                last_text = t
        elif isinstance(m, ResultMessage):
            _accumulate(metrics, m, is_worker=True)
    return last_text


async def run_worker(worker_model, advisor_model, workdir, spec, metrics, max_turns: int = 40) -> None:
    """하니스 owner 루프. solo arm은 worker 단독, advisor arm은 라운드마다 Fable 상담 주입."""
    opts = build_worker_options(worker_model, workdir, max_turns)
    async with ClaudeSDKClient(options=opts) as worker:
        if advisor_model is None:
            await worker.query(WORKER_INSTRUCTIONS.format(workdir=str(workdir), spec=spec))
            await _drain_turn(worker, metrics)
            return

        # 라운드 0: 착수 전 반드시 advisor에게 빌드 플랜을 받아 주입.
        advice = await consult_advisor(
            advisor_model, "Give a numbered build plan for this RealWorld backend.", spec, metrics
        )
        await worker.query(
            WORKER_INSTRUCTIONS.format(workdir=str(workdir), spec=spec)
            + f"\n\nAdvisor's build plan:\n{advice}"
        )
        last = await _drain_turn(worker, metrics)

        # 이후 라운드: worker 진행상황을 advisor에게 리뷰받아 다음 스텝을 주입.
        for _ in range(MAX_ADVISOR_ROUNDS - 1):
            advice = await consult_advisor(
                advisor_model,
                "Review the worker's progress and give the next numbered steps to reach a "
                "passing server.",
                last,
                metrics,
            )
            await worker.query(WORKER_CONTINUE.format(advice=advice))
            last = await _drain_turn(worker, metrics)
