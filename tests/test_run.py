from harness import run as R
from harness import models


def test_arms_defined():
    keys = {a["key"] for a in R.ARMS}
    assert keys == {"haiku-solo", "sonnet-solo", "fable-solo", "haiku+fable",
                    "sonnet+fable", "opus-solo", "deleg-opus", "plan-fable-haiku"}
    hf = next(a for a in R.ARMS if a["key"] == "haiku+fable")
    assert hf["worker"] == models.HAIKU and hf["advisor"] == models.FABLE
    hs = next(a for a in R.ARMS if a["key"] == "haiku-solo")
    assert hs["advisor"] is None


def test_opus_and_delegate_arms_defined():
    osolo = next(a for a in R.ARMS if a["key"] == "opus-solo")
    assert osolo["worker"] == models.OPUS and osolo["advisor"] is None
    dg = next(a for a in R.ARMS if a["key"] == "deleg-opus")
    assert dg["worker"] == models.OPUS and dg["advisor"] == models.SONNET
    assert dg["mode"] == "delegate"
    # Plan-then-Execute: Fable 플래너 + Haiku 실행자
    pf = next(a for a in R.ARMS if a["key"] == "plan-fable-haiku")
    assert pf["worker"] == models.HAIKU and pf["advisor"] == models.FABLE
    assert pf["mode"] == "delegate"


def test_drive_worker_routes_delegate(monkeypatch):
    calls = {}
    monkeypatch.setattr(R, "run_delegator",
                        lambda *a, **k: calls.setdefault("deleg", a) or None)
    monkeypatch.setattr(R, "run_worker",
                        lambda *a, **k: calls.setdefault("solo", a) or None)
    monkeypatch.setattr(R.asyncio, "run", lambda coro: coro)  # 코루틴 미실행, 라우팅만 검증
    dg = next(a for a in R.ARMS if a["key"] == "deleg-opus")
    R._drive_worker(dg, "/tmp/wd", "spec", object(), 10)
    assert "deleg" in calls and "solo" not in calls


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
    assert out["fallback_used"] is False  # opus 미사용
    assert (tmp_path / "haiku-solo-0.json").exists()
