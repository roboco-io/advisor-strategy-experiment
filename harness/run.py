"""arm 정의·오케스트레이션·CLI (Agent SDK + 구독 실행)."""
from __future__ import annotations
import argparse
import asyncio
import os
import tempfile
import time

from harness import models, grade
from harness.metrics import RunMetrics
from harness.worker import run_worker

ARMS = [
    {"key": "haiku-solo", "worker": models.HAIKU, "advisor": None},
    {"key": "sonnet-solo", "worker": models.SONNET, "advisor": None},
    {"key": "fable-solo", "worker": models.FABLE, "advisor": None},
    {"key": "haiku+fable", "worker": models.HAIKU, "advisor": models.FABLE},
    {"key": "sonnet+fable", "worker": models.SONNET, "advisor": models.FABLE},
]


def _use_subscription() -> None:
    """API 키 과금 대신 구독 인증을 쓰도록 ANTHROPIC_API_KEY를 제거."""
    os.environ.pop("ANTHROPIC_API_KEY", None)


def _drive_worker(arm, workdir, spec, metrics, max_turns) -> None:
    """라이브 worker를 동기적으로 구동(테스트에서 monkeypatch 대상)."""
    asyncio.run(run_worker(arm["worker"], arm["advisor"], workdir, spec, metrics, max_turns))


def run_arm(arm, spec, collection_path, results_dir,
            grade_fn=grade.grade, n_index: int = 0, max_turns: int = 60) -> dict:
    os.makedirs(results_dir, exist_ok=True)
    _use_subscription()
    metrics = RunMetrics(arm=arm["key"])
    workdir = tempfile.mkdtemp(prefix=f"{arm['key']}-{n_index}-")

    start = time.monotonic()
    _drive_worker(arm, workdir, spec, metrics, max_turns)
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
    ap.add_argument("--max-turns", type=int, default=60)
    args = ap.parse_args()

    _use_subscription()
    spec = open(args.spec).read()
    selected = ARMS if args.arms == "all" else [a for a in ARMS if a["key"] in args.arms.split(",")]

    for i in range(args.n):
        for arm in selected:
            print(f"[run {i}] arm={arm['key']} ...")
            try:
                res = run_arm(
                    arm, spec, args.collection, args.results_dir,
                    n_index=i, max_turns=args.max_turns,
                )
            except Exception as e:  # noqa: BLE001 - 한 arm 실패가 배치 전체를 중단시키지 않도록
                print(f"  ERROR arm={arm['key']} n={i}: {e}")
                continue
            g = res["grade"] or {}
            print(f"  pass={g.get('passed')}/{g.get('total')} cost=${res['total_cost']:.2f} "
                  f"(sdk~${res['sdk_cost_usd']:.2f}) turns={res['worker_turns']} "
                  f"advisor={res['advisor_calls']}")


if __name__ == "__main__":
    main()
