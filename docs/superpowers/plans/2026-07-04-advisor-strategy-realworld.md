# Advisor Strategy RealWorld 실험 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fable-advisor + Haiku/Sonnet-worker 커스텀 오케스트레이션 하니스를 만들어, 각 arm이 RealWorld(Conduit) 백엔드를 구현하고 Newman으로 채점받아 승격폭·비용을 계측한다.

**Architecture:** Python 하니스가 arm별로 격리된 workdir에서 worker 에이전트 루프를 돌린다. worker는 Anthropic 정의 bash/text_editor 도구로 Node/Express/SQLite 백엔드를 작성·실행하고, advisor arm에서는 `consult_advisor` 커스텀 도구로 Fable에게 조언을 받는다. 종료 후 하니스가 서버를 기동해 공식 Newman e2e 컬렉션을 실행하고 pass율·토큰·비용을 JSON으로 기록한다.

**Tech Stack:** Python 3.12+, uv, `anthropic` SDK, pytest, Node.js(워커 산출물 실행용), newman(npm).

## Global Constraints

- Python 3.12+, 패키지 관리는 uv. 의존성: `anthropic`, `pytest`(dev).
- 모델 ID는 정확히: advisor `claude-fable-5`, worker `claude-haiku-4-5` / `claude-sonnet-5`, fallback `claude-opus-4-8`. 날짜 접미사 금지.
- Fable 호출은 `thinking` 파라미터 생략(상시 ON), `betas=["server-side-fallback-2026-06-01"]` + `fallbacks=[{"model":"claude-opus-4-8"}]` 포함, `stop_reason=="refusal"` 분기 필수.
- Haiku는 `effort` 파라미터 사용 금지(400 에러). Sonnet은 `effort` 사용 가능.
- bash/text_editor는 Anthropic 정의·client-executed. bash는 `{"type":"bash_20250124","name":"bash"}`, editor는 `{"type":"text_editor_20250728","name":"str_replace_based_edit_tool"}` — `input_schema` 붙이지 않는다.
- 모든 파일 경로는 리포 루트(`advisor-strategy-test/`) 기준.
- 툴 입력의 `input`은 반드시 파싱된 객체로 다루고 raw 문자열 매칭 금지. bash 명령은 workdir 샌드박스·타임아웃·allowlist 적용.
- 테스트는 라이브 API를 호출하지 않는다(마지막 파일럿 태스크 제외). anthropic 클라이언트는 목/페이크로 대체.

## File Structure

- `pyproject.toml` — uv 프로젝트·의존성.
- `harness/__init__.py`
- `harness/models.py` — 모델 상수·단가·비용 계산.
- `harness/metrics.py` — usage 누적·비용·JSON 기록.
- `harness/tools.py` — bash/text_editor 샌드박스 실행·도구 정의·tool_use 디스패치.
- `harness/advisor.py` — Fable 호출·fallback·`consult_advisor` 도구·프롬프트.
- `harness/worker.py` — executor 에이전트 루프.
- `harness/grade.py` — 서버 기동·newman 실행·pass 집계.
- `harness/run.py` — arm 정의·오케스트레이션·CLI.
- `tasks/realworld_spec.md` — 워커에 주는 RealWorld API 스펙(테스트 컬렉션 제외).
- `tests/` — 각 모듈 단위 테스트.

---

### Task 1: 프로젝트 스캐폴드 + models.py

**Files:**
- Create: `pyproject.toml`, `harness/__init__.py`, `harness/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `FABLE="claude-fable-5"`, `HAIKU="claude-haiku-4-5"`, `SONNET="claude-sonnet-5"`, `OPUS="claude-opus-4-8"`; `PRICES: dict[str, tuple[float, float]]` (입력,출력 $/1M); `cost_of(model: str, input_tokens: int, output_tokens: int, cache_read: int = 0, cache_write: int = 0) -> float`.

- [ ] **Step 1: 프로젝트 초기화**

Run:
```bash
cd /Users/dohyunjung/Workspace/roboco-io/research/advisor-strategy-test
uv init --no-workspace --name advisor-strategy-test
uv add anthropic
uv add --dev pytest
mkdir -p harness tests tasks
touch harness/__init__.py
```
Expected: `pyproject.toml`, `.venv` 생성, `anthropic`·`pytest` 설치.

- [ ] **Step 2: 실패 테스트 작성** — `tests/test_models.py`

```python
from harness import models


def test_model_ids():
    assert models.FABLE == "claude-fable-5"
    assert models.HAIKU == "claude-haiku-4-5"
    assert models.SONNET == "claude-sonnet-5"
    assert models.OPUS == "claude-opus-4-8"


def test_cost_of_haiku():
    # Haiku: $1/1M in, $5/1M out
    c = models.cost_of(models.HAIKU, input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(c - 6.0) < 1e-9


def test_cost_of_fable_with_cache():
    # Fable: $10 in, $50 out; cache_read ~0.1x in, cache_write ~1.25x in
    c = models.cost_of(
        models.FABLE, input_tokens=1_000_000, output_tokens=0,
        cache_read=1_000_000, cache_write=1_000_000,
    )
    # 10 (in) + 1.0 (read 0.1x) + 12.5 (write 1.25x) = 23.5
    assert abs(c - 23.5) < 1e-6
```

- [ ] **Step 3: 실패 확인**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError` 또는 `AttributeError`.

- [ ] **Step 4: 구현** — `harness/models.py`

```python
"""모델 ID, 단가($/1M 토큰), 비용 계산."""

FABLE = "claude-fable-5"
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-5"
OPUS = "claude-opus-4-8"

# (input $/1M, output $/1M). Sonnet는 2026-08-31까지 도입가 2/10.
PRICES: dict[str, tuple[float, float]] = {
    FABLE: (10.0, 50.0),
    HAIKU: (1.0, 5.0),
    SONNET: (2.0, 10.0),  # 도입가; 만료 후 3/15로 갱신
    OPUS: (5.0, 25.0),
}

_M = 1_000_000


def cost_of(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read: int = 0,
    cache_write: int = 0,
) -> float:
    """토큰 사용량을 단가로 환산. cache_read≈0.1x, cache_write≈1.25x(5분 TTL) 입력단가."""
    in_price, out_price = PRICES[model]
    return (
        input_tokens / _M * in_price
        + output_tokens / _M * out_price
        + cache_read / _M * in_price * 0.1
        + cache_write / _M * in_price * 1.25
    )
```

- [ ] **Step 5: 통과 확인**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock harness/__init__.py harness/models.py tests/test_models.py
git commit -m "feat: 프로젝트 스캐폴드 및 모델 단가/비용 계산"
```

---

### Task 2: metrics.py

**Files:**
- Create: `harness/metrics.py`
- Test: `tests/test_metrics.py`

**Interfaces:**
- Consumes: `models.cost_of`.
- Produces: `RunMetrics` dataclass. 메서드: `add_usage(model: str, usage) -> None`(usage는 `.input_tokens`,`.output_tokens`,`.cache_read_input_tokens`,`.cache_creation_input_tokens` 속성 보유 객체 또는 dict), `note_advisor_call() -> None`, `note_turn() -> None`, `note_refusal(category: str | None) -> None`, `to_dict() -> dict`, `save(path: str) -> None`. 필드: `arm: str`, `total_cost: float`, `by_model: dict[str, dict]`, `advisor_calls: int`, `worker_turns: int`, `refusals: list`, `wall_clock_s: float`, `grade: dict | None`.

- [ ] **Step 1: 실패 테스트** — `tests/test_metrics.py`

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/metrics.py`

```python
"""run별 계측 수집·비용 환산·JSON 기록."""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from harness import models


def _get(usage, key, default=0):
    if isinstance(usage, dict):
        return usage.get(key, default) or default
    return getattr(usage, key, default) or default


@dataclass
class RunMetrics:
    arm: str
    total_cost: float = 0.0
    by_model: dict = field(default_factory=dict)
    advisor_calls: int = 0
    worker_turns: int = 0
    refusals: list = field(default_factory=list)
    wall_clock_s: float = 0.0
    grade: dict | None = None

    def add_usage(self, model: str, usage) -> None:
        i = _get(usage, "input_tokens")
        o = _get(usage, "output_tokens")
        cr = _get(usage, "cache_read_input_tokens")
        cw = _get(usage, "cache_creation_input_tokens")
        self.total_cost += models.cost_of(model, i, o, cr, cw)
        b = self.by_model.setdefault(
            model, {"input_tokens": 0, "output_tokens": 0, "cache_read": 0, "cache_write": 0, "calls": 0}
        )
        b["input_tokens"] += i
        b["output_tokens"] += o
        b["cache_read"] += cr
        b["cache_write"] += cw
        b["calls"] += 1

    def note_advisor_call(self) -> None:
        self.advisor_calls += 1

    def note_turn(self) -> None:
        self.worker_turns += 1

    def note_refusal(self, category) -> None:
        self.refusals.append(category)

    def to_dict(self) -> dict:
        return {
            "arm": self.arm,
            "total_cost": round(self.total_cost, 6),
            "by_model": self.by_model,
            "advisor_calls": self.advisor_calls,
            "worker_turns": self.worker_turns,
            "refusals": self.refusals,
            "wall_clock_s": round(self.wall_clock_s, 2),
            "grade": self.grade,
        }

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: 커밋**

```bash
git add harness/metrics.py tests/test_metrics.py
git commit -m "feat: run 계측 수집 및 JSON 기록"
```

---

### Task 3: tools.py — bash/text_editor 샌드박스

**Files:**
- Create: `harness/tools.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Produces:
  - `BASH_TOOL = {"type": "bash_20250124", "name": "bash"}`
  - `EDITOR_TOOL = {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}`
  - `class Sandbox(workdir: str, timeout: int = 120)` — `.run_bash(inp: dict) -> str`, `.edit(inp: dict) -> str`.
  - `handle_tool_use(block, sandbox) -> dict` — `tool_use` 블록(`.name`,`.input`,`.id` 보유)을 받아 `{"type":"tool_result","tool_use_id":...,"content":...,"is_error":bool}` 반환. `bash`/`str_replace_based_edit_tool` 이외 이름은 `is_error=True`.

- [ ] **Step 1: 실패 테스트** — `tests/test_tools.py`

```python
from harness import tools


class Block:
    def __init__(self, name, inp, id="t1"):
        self.name, self.input, self.id = name, inp, id


def test_bash_runs_in_workdir(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    out = sb.run_bash({"command": "echo hi > f.txt && cat f.txt"})
    assert "hi" in out
    assert (tmp_path / "f.txt").read_text().strip() == "hi"


def test_editor_create_and_path_traversal_blocked(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    ok = sb.edit({"command": "create", "path": "app.js", "file_text": "x=1"})
    assert (tmp_path / "app.js").exists()
    res = sb.edit({"command": "create", "path": "../evil.js", "file_text": "bad"})
    assert "error" in res.lower() or "denied" in res.lower()


def test_handle_tool_use_dispatch(tmp_path):
    sb = tools.Sandbox(str(tmp_path))
    r = tools.handle_tool_use(Block("bash", {"command": "echo ok"}), sb)
    assert r["type"] == "tool_result"
    assert r["tool_use_id"] == "t1"
    assert not r.get("is_error")
    bad = tools.handle_tool_use(Block("unknown", {}), sb)
    assert bad["is_error"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/tools.py`

```python
"""Anthropic 정의 bash/text_editor 도구의 client-side 샌드박스 실행."""
from __future__ import annotations
import os
import subprocess

BASH_TOOL = {"type": "bash_20250124", "name": "bash"}
EDITOR_TOOL = {"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}


class Sandbox:
    def __init__(self, workdir: str, timeout: int = 120):
        self.workdir = os.path.realpath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.timeout = timeout

    def _resolve(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.workdir, path))
        if full != self.workdir and not full.startswith(self.workdir + os.sep):
            raise ValueError(f"path escapes workdir: {path}")
        return full

    def run_bash(self, inp: dict) -> str:
        if inp.get("restart"):
            return "bash session restarted"
        cmd = inp["command"]
        try:
            p = subprocess.run(
                cmd, shell=True, cwd=self.workdir, capture_output=True,
                text=True, timeout=self.timeout,
            )
            return (p.stdout + p.stderr)[:20000] or "(no output)"
        except subprocess.TimeoutExpired:
            return f"error: command timed out after {self.timeout}s"

    def edit(self, inp: dict) -> str:
        cmd = inp["command"]
        try:
            path = self._resolve(inp["path"])
        except (ValueError, KeyError) as e:
            return f"error: {e}"
        if cmd == "view":
            if os.path.isdir(path):
                return "\n".join(sorted(os.listdir(path)))
            with open(path) as f:
                return f.read()[:20000]
        if cmd == "create":
            os.makedirs(os.path.dirname(path) or self.workdir, exist_ok=True)
            with open(path, "w") as f:
                f.write(inp.get("file_text", ""))
            return f"created {inp['path']}"
        if cmd == "str_replace":
            with open(path) as f:
                text = f.read()
            old, new = inp["old_str"], inp["new_str"]
            if text.count(old) != 1:
                return "error: old_str must match exactly once"
            with open(path, "w") as f:
                f.write(text.replace(old, new))
            return "edited"
        if cmd == "insert":
            with open(path) as f:
                lines = f.readlines()
            lines.insert(inp["insert_line"], inp["insert_text"] + "\n")
            with open(path, "w") as f:
                f.writelines(lines)
            return "inserted"
        return f"error: unknown command {cmd}"


def handle_tool_use(block, sandbox: Sandbox) -> dict:
    name = block.name
    result = {"type": "tool_result", "tool_use_id": block.id}
    try:
        if name == "bash":
            result["content"] = sandbox.run_bash(block.input)
        elif name == "str_replace_based_edit_tool":
            content = sandbox.edit(block.input)
            result["content"] = content
            if isinstance(content, str) and content.startswith("error:"):
                result["is_error"] = True
        else:
            result["content"] = f"error: unknown tool {name}"
            result["is_error"] = True
    except Exception as e:  # noqa: BLE001 - 도구 오류는 모델에 되돌려줌
        result["content"] = f"error: {e}"
        result["is_error"] = True
    return result
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_tools.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: 커밋**

```bash
git add harness/tools.py tests/test_tools.py
git commit -m "feat: bash/text_editor 샌드박스 도구 실행"
```

---

### Task 4: advisor.py — Fable 조언자

**Files:**
- Create: `harness/advisor.py`
- Test: `tests/test_advisor.py`

**Interfaces:**
- Consumes: `metrics.RunMetrics`, `models.FABLE/OPUS`.
- Produces:
  - `CONSULT_ADVISOR_TOOL` — 커스텀 도구 정의 dict(`name="consult_advisor"`, `input_schema`: `question`(str, required), `context`(str, optional)).
  - `ADVISOR_SYSTEM` — 조언자 시스템 프롬프트 상수.
  - `class Advisor(client, metrics, model=models.FABLE)` — `.consult(question: str, context: str = "") -> str`. Fable Messages API 호출(`thinking` 생략, fallback 파라미터 포함), `stop_reason=="refusal"` 시 `metrics.note_refusal(category)` 후 `"advisor declined"` 반환. usage를 metrics에 기록, `metrics.note_advisor_call()` 호출.

- [ ] **Step 1: 실패 테스트** — `tests/test_advisor.py`

```python
from harness.advisor import Advisor, CONSULT_ADVISOR_TOOL
from harness.metrics import RunMetrics


class FakeBlock:
    type = "text"
    text = "1. Add JWT auth\n2. Create /api/users"


class FakeUsage:
    input_tokens = 100
    output_tokens = 30
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 0


class FakeResp:
    stop_reason = "end_turn"
    content = [FakeBlock()]
    usage = FakeUsage()


class FakeMessages:
    def __init__(self, resp):
        self._resp = resp
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._resp


class FakeClient:
    def __init__(self, resp):
        self.beta = type("B", (), {"messages": FakeMessages(resp)})()


def test_consult_returns_advice_and_records():
    m = RunMetrics(arm="haiku+fable")
    client = FakeClient(FakeResp())
    adv = Advisor(client, m)
    out = adv.consult("How to start?", context="empty repo")
    assert "JWT" in out
    assert m.advisor_calls == 1
    assert m.by_model["claude-fable-5"]["calls"] == 1
    # fallback 파라미터가 요청에 포함됐는지
    kw = client.beta.messages.last_kwargs
    assert kw["model"] == "claude-fable-5"
    assert kw.get("fallbacks") == [{"model": "claude-opus-4-8"}]
    assert "thinking" not in kw


def test_consult_handles_refusal():
    class Refused(FakeResp):
        stop_reason = "refusal"
        content = []
        stop_details = type("S", (), {"category": "cyber"})()

    m = RunMetrics(arm="haiku+fable")
    adv = Advisor(FakeClient(Refused()), m)
    out = adv.consult("q")
    assert "declined" in out.lower()
    assert m.refusals == ["cyber"]


def test_tool_def():
    assert CONSULT_ADVISOR_TOOL["name"] == "consult_advisor"
    assert "question" in CONSULT_ADVISOR_TOOL["input_schema"]["properties"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_advisor.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/advisor.py`

```python
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
        self.metrics.add_usage(self.model, resp.usage)
        if resp.stop_reason == "refusal":
            category = getattr(getattr(resp, "stop_details", None), "category", None)
            self.metrics.note_refusal(category)
            return "advisor declined to respond"
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_advisor.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: 커밋**

```bash
git add harness/advisor.py tests/test_advisor.py
git commit -m "feat: Fable 조언자 및 consult_advisor 도구"
```

---

### Task 5: worker.py — executor 에이전트 루프

**Files:**
- Create: `harness/worker.py`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `tools.BASH_TOOL/EDITOR_TOOL/handle_tool_use/Sandbox`, `advisor.CONSULT_ADVISOR_TOOL/Advisor`, `metrics.RunMetrics`, `models`.
- Produces:
  - `WORKER_SYSTEM` 상수.
  - `run_worker(client, worker_model: str, sandbox, metrics, spec: str, advisor=None, max_turns: int = 50, max_advisor_calls: int = 3) -> str` — executor 루프 실행, 최종 assistant 텍스트 반환. advisor가 None이면 solo arm(consult 도구 미제공). `worker_model`이 SONNET이면 `output_config={"effort":"high"}` 추가, HAIKU면 미추가. 각 API 응답마다 `metrics.add_usage`·`metrics.note_turn`. `consult_advisor` tool_use는 `advisor.consult(...)`로 처리하고 `max_advisor_calls` 초과 시 거절 메시지 반환.

- [ ] **Step 1: 실패 테스트** — `tests/test_worker.py`

```python
from harness.worker import run_worker
from harness import tools as T
from harness.metrics import RunMetrics
from harness import models


class TU:
    def __init__(self, name, inp, id):
        self.type = "tool_use"; self.name = name; self.input = inp; self.id = id


class TX:
    def __init__(self, text):
        self.type = "text"; self.text = text


class Usage:
    input_tokens = 10; output_tokens = 5
    cache_read_input_tokens = 0; cache_creation_input_tokens = 0


class Resp:
    def __init__(self, content, stop):
        self.content = content; self.stop_reason = stop; self.usage = Usage()


class ScriptedMessages:
    """정해진 순서로 응답을 내주는 페이크."""
    def __init__(self, script):
        self.script = list(script); self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.script.pop(0)


class Client:
    def __init__(self, script):
        self.messages = ScriptedMessages(script)


def test_worker_uses_bash_then_finishes(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    script = [
        Resp([TU("bash", {"command": "echo built > done.txt"}, "u1")], "tool_use"),
        Resp([TX("done")], "end_turn"),
    ]
    m = RunMetrics(arm="haiku-solo")
    final = run_worker(Client(script), models.HAIKU, sb, m, spec="build it")
    assert "done" in final
    assert (tmp_path / "done.txt").exists()
    assert m.worker_turns == 2
    # Haiku는 effort 미포함
    assert "output_config" not in m and all(
        "output_config" not in c for c in Client(script).messages.calls
    ) or True  # effort는 kwargs로 확인 (아래 별도 테스트)


def test_sonnet_includes_effort(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    client = Client([Resp([TX("ok")], "end_turn")])
    run_worker(client, models.SONNET, sb, RunMetrics(arm="sonnet-solo"), spec="x")
    assert client.messages.calls[0].get("output_config", {}).get("effort") == "high"


def test_haiku_omits_effort(tmp_path):
    sb = T.Sandbox(str(tmp_path))
    client = Client([Resp([TX("ok")], "end_turn")])
    run_worker(client, models.HAIKU, sb, RunMetrics(arm="haiku-solo"), spec="x")
    assert "output_config" not in client.messages.calls[0]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/worker.py`

```python
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

    base_kwargs = {"model": worker_model, "max_tokens": 8000, "system": WORKER_SYSTEM, "tools": tool_defs}
    if worker_model == models.SONNET:
        base_kwargs["output_config"] = {"effort": "high"}

    for _ in range(max_turns):
        resp = client.messages.create(messages=messages, **base_kwargs)
        metrics.note_turn()
        metrics.add_usage(worker_model, resp.usage)
        messages.append({"role": "assistant", "content": resp.content})

        final_text = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ) or final_text

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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_worker.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: 커밋**

```bash
git add harness/worker.py tests/test_worker.py
git commit -m "feat: executor 에이전트 루프"
```

---

### Task 6: grade.py — 서버 기동 + Newman 채점

**Files:**
- Create: `harness/grade.py`
- Test: `tests/test_grade.py`

**Interfaces:**
- Produces:
  - `parse_newman_json(report: dict) -> dict` — newman JSON 리포트(`run.stats.assertions`)에서 `{"total": int, "passed": int, "failures": [str]}` 추출.
  - `grade(workdir: str, collection_path: str, port: int = 3000, boot_cmd: str = "npm start", boot_timeout: int = 30) -> dict` — `npm install` → 서버 백그라운드 기동 → 헬스체크 → `newman run <collection> --reporters json` 실행 → `parse_newman_json` 반환. 서버 기동 실패 시 `{"server_ok": False, "total": 0, "passed": 0, "failures": ["server did not boot"]}`. (외부 프로세스 의존이므로 단위 테스트는 `parse_newman_json`만 검증.)

- [ ] **Step 1: 실패 테스트** — `tests/test_grade.py`

```python
from harness.grade import parse_newman_json


def test_parse_newman_stats():
    report = {
        "run": {
            "stats": {"assertions": {"total": 10, "failed": 3}},
            "failures": [
                {"error": {"test": "GET /api/articles returns 200"}},
                {"error": {"test": "auth returns token"}},
                {"error": {"test": "x"}},
            ],
        }
    }
    r = parse_newman_json(report)
    assert r["total"] == 10
    assert r["passed"] == 7
    assert len(r["failures"]) == 3
    assert "GET /api/articles returns 200" in r["failures"][0]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/grade.py`

```python
"""서버 기동 + Newman e2e 채점."""
from __future__ import annotations
import json
import os
import subprocess
import time
import urllib.request


def parse_newman_json(report: dict) -> dict:
    stats = report.get("run", {}).get("stats", {}).get("assertions", {})
    total = stats.get("total", 0)
    failed = stats.get("failed", 0)
    failures = [
        f.get("error", {}).get("test", "unknown")
        for f in report.get("run", {}).get("failures", [])
    ]
    return {"total": total, "passed": total - failed, "failures": failures}


def _wait_health(port: int, timeout: int) -> bool:
    url = f"http://localhost:{port}/api/tags"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:  # noqa: BLE001
            time.sleep(1)
    return False


def grade(workdir, collection_path, port=3000, boot_cmd="npm start", boot_timeout=30) -> dict:
    fail = {"server_ok": False, "total": 0, "passed": 0, "failures": ["server did not boot"]}
    env = {**os.environ, "PORT": str(port)}
    subprocess.run("npm install", shell=True, cwd=workdir, env=env,
                   capture_output=True, text=True, timeout=300)
    proc = subprocess.Popen(boot_cmd, shell=True, cwd=workdir, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _wait_health(port, boot_timeout):
            return fail
        report_path = os.path.join(workdir, "newman-report.json")
        subprocess.run(
            f"newman run {collection_path} --reporters json "
            f"--reporter-json-export {report_path} "
            f"--env-var APIURL=http://localhost:{port}/api",
            shell=True, capture_output=True, text=True, timeout=300,
        )
        with open(report_path) as f:
            report = json.load(f)
        out = parse_newman_json(report)
        out["server_ok"] = True
        return out
    finally:
        proc.terminate()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_grade.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: 커밋**

```bash
git add harness/grade.py tests/test_grade.py
git commit -m "feat: 서버 기동 및 Newman 채점"
```

---

### Task 7: tasks/realworld_spec.md — 워커용 스펙

**Files:**
- Create: `tasks/realworld_spec.md`

**Interfaces:**
- Produces: worker에게 주는 RealWorld API 명세 문자열(테스트 컬렉션 원본 제외).

- [ ] **Step 1: 스펙 문서 작성** — `tasks/realworld_spec.md`

RealWorld 공식 API 명세 요약을 작성한다(엔드포인트·인증·응답 형태). 아래 내용을 그대로 채운다:

```markdown
# RealWorld (Conduit) Backend API Spec

Node.js + Express + SQLite로 아래 REST API를 구현하라. 서버는 `PORT` 환경변수(기본 3000)에서 기동되고, 모든 엔드포인트는 `/api` 프리픽스 아래에 둔다. `npm start`로 기동돼야 한다.

## 인증
- JWT 기반. `Authorization: Token <jwt>` 헤더.
- 응답의 User 객체: `{ user: { email, token, username, bio, image } }`.

## 엔드포인트
- POST `/api/users` — 회원가입 `{ user: { username, email, password } }`
- POST `/api/users/login` — 로그인 `{ user: { email, password } }`
- GET `/api/user` — 현재 사용자(인증 필요)
- PUT `/api/user` — 사용자 수정(인증)
- GET `/api/profiles/:username` — 프로필
- POST/DELETE `/api/profiles/:username/follow` — 팔로우/언팔로우(인증)
- GET `/api/articles` — 목록(필터: tag, author, favorited, limit, offset)
- GET `/api/articles/feed` — 팔로우 피드(인증)
- GET `/api/articles/:slug` — 단건
- POST `/api/articles` — 생성 `{ article: { title, description, body, tagList } }`(인증)
- PUT `/api/articles/:slug` — 수정(인증)
- DELETE `/api/articles/:slug` — 삭제(인증)
- POST/DELETE `/api/articles/:slug/favorite` — 즐겨찾기(인증)
- GET `/api/articles/:slug/comments` — 댓글 목록
- POST `/api/articles/:slug/comments` — 댓글 작성(인증)
- DELETE `/api/articles/:slug/comments/:id` — 댓글 삭제(인증)
- GET `/api/tags` — 태그 목록

## 응답 형태
- Article: `{ article: { slug, title, description, body, tagList, createdAt, updatedAt, favorited, favoritesCount, author: {username,bio,image,following} } }`
- 목록은 `{ articles: [...], articlesCount: N }`.
- 검증 오류: 422 `{ errors: { body: ["can't be blank"] } }`.

전체 공식 명세: https://realworld-docs.netlify.app/specifications/backend/endpoints/
스펙을 만족하는 실행 가능한 서버를 목표로 하라.
```

- [ ] **Step 2: 커밋**

```bash
git add tasks/realworld_spec.md
git commit -m "docs: 워커용 RealWorld API 스펙"
```

---

### Task 8: run.py — arm 오케스트레이션 + CLI

**Files:**
- Create: `harness/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: 전 모듈.
- Produces:
  - `ARMS: list[dict]` — 5개 arm 정의. 각 `{"key": str, "worker": model, "advisor": model | None}`.
  - `run_arm(arm: dict, spec: str, collection_path: str, results_dir: str, client_factory, grade_fn=grade.grade, n_index: int = 0) -> dict` — 격리 workdir 생성 → worker 실행 → 채점 → metrics.save → dict 반환. `client_factory()`는 anthropic 클라이언트 반환(테스트에서 페이크 주입). wall-clock 측정.
  - `main()` — CLI: `--arms`(쉼표 구분, 기본 전체), `--n`(반복, 기본 1), `--results-dir`, `--collection`. 순차 실행.

- [ ] **Step 1: 실패 테스트** — `tests/test_run.py`

```python
from harness import run as R
from harness import models


def test_arms_defined():
    keys = {a["key"] for a in R.ARMS}
    assert keys == {"haiku-solo", "sonnet-solo", "fable-solo", "haiku+fable", "sonnet+fable"}
    hf = next(a for a in R.ARMS if a["key"] == "haiku+fable")
    assert hf["worker"] == models.HAIKU and hf["advisor"] == models.FABLE
    hs = next(a for a in R.ARMS if a["key"] == "haiku-solo")
    assert hs["advisor"] is None


def test_run_arm_end_to_end(tmp_path, monkeypatch):
    # worker/grade를 페이크로 대체해 오케스트레이션만 검증
    def fake_run_worker(*a, **k):
        return "done"

    def fake_grade(workdir, collection_path, **k):
        return {"server_ok": True, "total": 10, "passed": 8, "failures": []}

    monkeypatch.setattr(R, "run_worker", fake_run_worker)
    arm = {"key": "haiku-solo", "worker": models.HAIKU, "advisor": None}
    out = R.run_arm(
        arm, spec="x", collection_path="c.json", results_dir=str(tmp_path),
        client_factory=lambda: object(), grade_fn=fake_grade,
    )
    assert out["arm"] == "haiku-solo"
    assert out["grade"]["passed"] == 8
    assert (tmp_path / "haiku-solo-0.json").exists()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `harness/run.py`

```python
"""arm 정의·오케스트레이션·CLI."""
from __future__ import annotations
import argparse
import os
import tempfile
import time

from harness import models, grade
from harness.metrics import RunMetrics
from harness.tools import Sandbox
from harness.advisor import Advisor
from harness.worker import run_worker

ARMS = [
    {"key": "haiku-solo", "worker": models.HAIKU, "advisor": None},
    {"key": "sonnet-solo", "worker": models.SONNET, "advisor": None},
    {"key": "fable-solo", "worker": models.FABLE, "advisor": None},
    {"key": "haiku+fable", "worker": models.HAIKU, "advisor": models.FABLE},
    {"key": "sonnet+fable", "worker": models.SONNET, "advisor": models.FABLE},
]


def run_arm(arm, spec, collection_path, results_dir, client_factory,
            grade_fn=grade.grade, n_index: int = 0) -> dict:
    os.makedirs(results_dir, exist_ok=True)
    metrics = RunMetrics(arm=arm["key"])
    workdir = tempfile.mkdtemp(prefix=f"{arm['key']}-{n_index}-")
    client = client_factory()
    advisor = Advisor(client, metrics, model=arm["advisor"]) if arm["advisor"] else None
    sandbox = Sandbox(workdir)

    start = time.monotonic()
    run_worker(client, arm["worker"], sandbox, metrics, spec, advisor=advisor)
    metrics.grade = grade_fn(workdir, collection_path)
    metrics.wall_clock_s = time.monotonic() - start

    out_path = os.path.join(results_dir, f"{arm['key']}-{n_index}.json")
    metrics.save(out_path)
    return metrics.to_dict()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="all")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--collection", required=True)
    ap.add_argument("--spec", default="tasks/realworld_spec.md")
    args = ap.parse_args()

    import anthropic
    spec = open(args.spec).read()
    selected = ARMS if args.arms == "all" else [a for a in ARMS if a["key"] in args.arms.split(",")]

    for i in range(args.n):
        for arm in selected:
            print(f"[run {i}] arm={arm['key']} ...")
            res = run_arm(
                arm, spec, args.collection, args.results_dir,
                client_factory=lambda: anthropic.Anthropic(), n_index=i,
            )
            g = res["grade"] or {}
            print(f"  pass={g.get('passed')}/{g.get('total')} cost=${res['total_cost']:.2f} "
                  f"turns={res['worker_turns']} advisor={res['advisor_calls']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_run.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: 전체 테스트 확인**

Run: `uv run pytest -v`
Expected: 모든 테스트 PASS.

- [ ] **Step 6: 커밋**

```bash
git add harness/run.py tests/test_run.py
git commit -m "feat: arm 오케스트레이션 및 CLI"
```

---

### Task 9: 라이브 파일럿 스모크 (N=1, 실제 API)

**Files:**
- Create: `README.md`(실행법), `results/`(gitignore 대상)

**Interfaces:**
- Consumes: 전체 하니스.

- [ ] **Step 1: 사전 요건 확인**

Run:
```bash
node --version && npm --version
npm install -g newman
uv run python -c "import anthropic; print('sdk ok')"
```
그리고 `ANTHROPIC_API_KEY` 또는 `ant auth status`로 인증 확인. Fable은 30일 데이터 보존이 필요하므로 조직 설정 확인.

- [ ] **Step 2: Newman 컬렉션 확보**

RealWorld 공식 Postman 컬렉션을 받아 `tasks/Conduit.postman_collection.json`으로 저장(공식 realworld 저장소의 api 폴더). 소스·버전을 README에 기록.

- [ ] **Step 3: 단일 arm 파일럿 (가장 저렴한 haiku-solo)**

Run:
```bash
uv run python -m harness.run --arms haiku-solo --collection tasks/Conduit.postman_collection.json --results-dir results
```
Expected: `results/haiku-solo-0.json` 생성, pass/total·cost 출력. 서버 기동 실패 시 grade.server_ok=False 확인 후 로그로 원인 파악.

- [ ] **Step 4: 전체 5 arm 파일럿**

Run:
```bash
uv run python -m harness.run --collection tasks/Conduit.postman_collection.json --results-dir results
```
Expected: 5개 `results/*-0.json`. 각 arm의 pass율·비용·advisor 호출수·turns 확인.

- [ ] **Step 5: 결과 요약 확인**

`results/*.json`을 읽어 승격폭(haiku-solo→haiku+fable Δpass·Δcost, sonnet 동)과 fable-solo 대비 위치를 수기 확인. 계측·채점이 타당하면 파일럿 성공.

- [ ] **Step 6: 커밋**

```bash
echo "results/" >> .gitignore
git add README.md .gitignore
git commit -m "docs: 실행법 및 파일럿 절차"
```

---

## Self-Review

**Spec coverage:**
- §3 모델/단가 → Task 1(models). §4 arms → Task 8(ARMS). §5.1 worker → Task 5. §5.2 advisor → Task 4. §5.3 metrics → Task 2. §5.4 grading → Task 6. §5.5 제어(max_turns/advisor_calls/sandbox) → Task 3·5. §6 N=1 파일럿 → Task 8(CLI --n)·Task 9. §7 산출물 → Task 9 Step 5. §8 파일 경계 → File Structure. tasks/realworld_spec.md → Task 7. ✅ 전 항목 태스크 매핑됨.

**Placeholder scan:** 각 코드 스텝에 실제 코드 포함. "적절한 오류처리" 류 없음. Task 7·9는 콘텐츠/명령 구체화됨.

**Type consistency:** `cost_of`(models)↔`add_usage`(metrics) 시그니처 일치. `Sandbox`/`handle_tool_use`(tools)↔worker 사용부 일치. `Advisor.consult`/`CONSULT_ADVISOR_TOOL`(advisor)↔worker 일치. `parse_newman_json`/`grade`(grade)↔`run_arm` 일치. `ARMS` 구조↔`run_arm` 일치. ✅
