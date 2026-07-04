"""Fable 조언자: consult_advisor 커스텀 도구 + Fable 호출·fallback·refusal 처리."""
from __future__ import annotations
from harness import models

ADVISOR_SYSTEM = (
    "You are an advisor to a coding agent building a RealWorld (Conduit) backend API. "
    "You cannot write code, edit files, or run tools. Respond in 100 words or fewer with "
    "a numbered list of concrete next steps. Give strategy, not implementations."
)

CONSULT_ADVISOR_TOOL = {
    "name": "consult_advisor",
    "description": (
        "Consult a stronger advisor model for strategic guidance. Call this before "
        "starting real work, when stuck, or to verify completion. Returns a short "
        "numbered list of steps."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "What you need advice on"},
            "context": {"type": "string", "description": "Relevant state, diffs, or errors"},
        },
        "required": ["question"],
    },
}


class Advisor:
    def __init__(self, client, metrics, model: str = models.FABLE, max_tokens: int = 2048):
        self.client = client
        self.metrics = metrics
        self.model = model
        self.max_tokens = max_tokens

    def consult(self, question: str, context: str = "") -> str:
        self.metrics.note_advisor_call()
        prompt = f"Question: {question}\n\nContext:\n{context}"
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=ADVISOR_SYSTEM,
            betas=["server-side-fallback-2026-06-01"],
            fallbacks=[{"model": models.OPUS}],
            messages=[{"role": "user", "content": prompt}],
        )
        served = getattr(resp, "model", None)
        served = served if served in models.PRICES else self.model
        self.metrics.add_usage(served, resp.usage)
        if resp.stop_reason == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            self.metrics.note_refusal(category)
            return "advisor declined to respond"
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
