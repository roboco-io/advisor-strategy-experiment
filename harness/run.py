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
