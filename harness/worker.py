"""executor 에이전트 루프."""
from __future__ import annotations
from harness import tools, models
from harness.advisor import CONSULT_ADVISOR_TOOL

WORKER_SYSTEM = (
    "You are a software engineer implementing a RealWorld (Conduit) backend API in "
    "Node.js + Express + SQLite. Use the bash and file editor tools to write code and "
    "run it. Your goal is a running server that satisfies the RealWorld API spec. "
    "Before real work, when stuck, and to verify completion, consult the advisor if "
    "available. When the server is complete and you have smoke-tested it, stop."
)


def _call_worker(client, worker_model, messages, base_kwargs, metrics):
    if worker_model == models.FABLE:
        resp = client.beta.messages.create(
            messages=messages,
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": models.OPUS}],
            **base_kwargs,
        )
    else:
        resp = client.messages.create(messages=messages, **base_kwargs)
    served = getattr(resp, "model", None)
    served = served if served in models.PRICES else worker_model
    metrics.add_usage(served, resp.usage)
    return resp


def run_worker(
    client, worker_model, sandbox, metrics, spec,
    advisor=None, max_turns: int = 50, max_advisor_calls: int = 3,
):
    tool_defs = [tools.BASH_TOOL, tools.EDITOR_TOOL]
    if advisor is not None:
        tool_defs.append(CONSULT_ADVISOR_TOOL)

    messages = [{"role": "user", "content": f"RealWorld API spec:\n\n{spec}"}]
    final_text = ""
    advisor_used = 0

    base_kwargs = {"model": worker_model, "max_tokens": 16000, "system": WORKER_SYSTEM, "tools": tool_defs}
    if worker_model == models.SONNET:
        base_kwargs["output_config"] = {"effort": "high"}

    for _ in range(max_turns):
        resp = _call_worker(client, worker_model, messages, base_kwargs, metrics)
        metrics.note_turn()
        messages.append({"role": "assistant", "content": resp.content})

        final_text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ) or final_text

        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            metrics.note_refusal(cat)
            break

        if resp.stop_reason in ("end_turn", "stop_sequence"):
            break

        if resp.stop_reason == "max_tokens":
            messages.append({"role": "user", "content": "Continue."})
            continue

        if resp.stop_reason != "tool_use":
            break

        results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == "consult_advisor" and advisor is not None:
                if advisor_used >= max_advisor_calls:
                    content = "advisor budget exhausted; proceed on your own"
                else:
                    advisor_used += 1
                    content = advisor.consult(
                        block.input.get("question", ""), block.input.get("context", "")
                    )
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": content}
                )
            else:
                results.append(tools.handle_tool_use(block, sandbox))
        messages.append({"role": "user", "content": results})

    return final_text
