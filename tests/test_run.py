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
    # 라이브 worker/grade를 페이크로 대체해 오케스트레이션만 검증
    def fake_drive(arm, workdir, spec, metrics, max_turns):
        metrics.worker_turns = 3
        metrics.add_usage(models.HAIKU, {"input_tokens": 100, "output_tokens": 20})

    def fake_grade(workdir, collection_path, **k):
        return {"server_ok": True, "total": 10, "passed": 8, "failures": []}

    monkeypatch.setattr(R, "_drive_worker", fake_drive)
    arm = {"key": "haiku-solo", "worker": models.HAIKU, "advisor": None}
    out = R.run_arm(
        arm, spec="x", collection_path="c.json", results_dir=str(tmp_path),
        grade_fn=fake_grade,
    )
    assert out["arm"] == "haiku-solo"
    assert out["grade"]["passed"] == 8
    assert out["worker_turns"] == 3
    assert (tmp_path / "haiku-solo-0.json").exists()
