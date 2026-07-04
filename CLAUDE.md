# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **measurement harness** for an experiment: does Anthropic's *Advisor Strategy* (a strong
model advises, a weak model owns the loop and executes) let a weak worker build a working
RealWorld/Conduit backend more cheaply than a strong model alone? Each **arm** runs a worker
agent that builds the backend, then the harness boots it and scores it with Newman, recording
per-model token usage → cost.

The app being built is a *benchmark vehicle*, not the deliverable. The deliverable is the
harness + the comparison across arms.

## Commands

```bash
uv run pytest -q                       # all tests (no live API calls)
uv run pytest tests/test_worker.py -v  # one file
uv run pytest tests/test_models.py::test_normalize_dated_and_alias -v   # one test

# live pilot (spends Claude Code subscription usage — run in an isolated env)
uv run python -m harness.run --collection tasks/Conduit.postman_collection.json
uv run python -m harness.run --arms haiku-solo,haiku+fable --n 1 \
  --collection tasks/Conduit.postman_collection.json --max-turns 60
```

`newman` is required for grading (`npm install -g newman`; on asdf run `asdf reshim nodejs`
or the shim won't resolve on PATH for the `grade.py` subprocess).

## Execution channel — the load-bearing design fact

The worker/advisor run via the **Claude Agent SDK (`claude-agent-sdk`) on Claude Code
subscription auth**, *not* the paid Messages API. `harness/run.py` **unsets
`ANTHROPIC_API_KEY`** at runtime (`_use_subscription`) so the SDK falls back to the on-disk
`~/.claude` login and draws on subscription usage instead of per-token API billing. If you
reintroduce an API key path, you reintroduce billing.

Cost is still measured: it's computed as `tokens × published price` (`models.cost_of`), so the
figure is independent of how the tokens were paid for. Dollar amounts are *computed, not
billed*. `sdk_cost_usd` is the SDK's own estimate, kept for cross-check.

There was an earlier raw-Messages-API implementation with a hand-rolled `tools.py` sandbox and
a `consult_advisor` tool loop — **it was deleted in the pivot**. Do not reintroduce a bash/file
sandbox: the Agent SDK provides `Bash`/`Read`/`Write`/`Edit`/`Glob`/`Grep` natively. History is
in `docs/superpowers/specs/…-design.md` §2.5.

## Architecture & data flow

`run.py` orchestrates; everything else is a focused unit it composes:

- **`models.py`** — model IDs, `PRICES`, `cost_of` (returns 0.0 for unmapped models — never
  crashes mid-run), `ALIAS` (full ID → SDK alias `"haiku"`/`"fable"`/…), and `normalize`
  (SDK `model_usage` keys are *dated* full IDs like `claude-haiku-4-5-20251001` → mapped to the
  `PRICES` key by prefix).
- **`metrics.py`** — `RunMetrics` accumulates cost/tokens. `add_model_usage(model_usage)` ingests
  the SDK's `ResultMessage.model_usage` (camelCase `inputTokens`/… keys), normalizes the model
  id, and accrues via `cost_of`. Serializes to per-run JSON.
- **`advisor.py`** — `advisor_agent(model)` returns an `AgentDefinition(model="fable", tools=[])`.
  The advisor is a **subagent the worker delegates to**, not a custom tool.
- **`worker.py`** — `build_options()` (pure: assembles `ClaudeAgentOptions` — model alias,
  `allowed_tools` + `"Agent"` and an `agents={"advisor": …}` *only* for advisor arms,
  `permission_mode="bypassPermissions"`, `fallback_model="opus"` when the worker is Fable),
  `is_advisor_call()`, `record_result()` (maps `ResultMessage` → metrics), and the async
  `run_worker()` live loop.
- **`grade.py`** — `parse_newman_json` (pure), and `grade` = `npm install` → boot server → health
  check `/api/tags` → `newman run` → parse. Boots in a new process group and `killpg`s it in
  `finally` (prevents orphaned servers holding port 3000 across arms). Non-boot / missing-report
  failures degrade to a structured dict, not an exception.
- **`run.py`** — `ARMS` (the 5 arms), `run_arm` (isolated tempdir → drive worker → grade → save),
  and `main` CLI.

Flow per arm: `run_arm` → `_drive_worker` (`asyncio.run(run_worker(...))`) → worker builds the
backend in a temp `cwd` → `ResultMessage.model_usage` folded into `RunMetrics` → `grade` runs
Newman → `results/<arm>-<n>.json`.

## Testing model

Tests **never hit the live API, Newman, or a real server**. The live surfaces are covered only
by the pilot run. Unit tests exercise the *pure* pieces: `build_options`, `is_advisor_call`,
`record_result`, `parse_newman_json`, `cost_of`/`normalize`, `add_model_usage`, and the arm
orchestration. The two monkeypatch seams are **`run._drive_worker`** (replace the async worker)
and the **`grade_fn` parameter** on `run_arm` (replace grading). If you need to test something
that currently only runs live, refactor it into a pure helper rather than mocking the SDK.

## Gotchas specific to this repo

- The worker executes **arbitrary LLM-generated bash with `bypassPermissions`** in a temp dir —
  no OS sandbox. Run the pilot in a container/VM/restricted user.
- Every SDK query carries ~24k cache-creation tokens of Claude Code system-prompt overhead —
  constant across arms (relative comparison holds; absolute cost includes it).
- No arm uses Opus; therefore any Opus usage in `by_model` means the Fable `fallback_model`
  fired — that's how `fallback_used` is derived in `run_arm`.
- To add an arm, edit `ARMS` in `run.py`; keep worker/advisor as `models.*` constants.
- The Newman collection is gothinkster's **legacy Postman** file (upstream moved to Bruno/Hurl);
  source pinned in `tasks/COLLECTION_SOURCE.txt`. `APIURL` is injected as `http://localhost:<port>/api`.

## Workflow artifacts

`docs/superpowers/specs/` and `docs/superpowers/plans/` hold the design spec and implementation
plan (this project was built via the Superpowers subagent-driven-development flow). `.superpowers/`
(git-ignored) holds the progress ledger and per-task briefs/reports — the ledger is the recovery
map for what's done.
