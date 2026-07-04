"""서버 기동 + Newman e2e 채점."""
from __future__ import annotations
import json
import os
import shlex
import signal
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


def _load_report(path: str) -> dict | None:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _free_port(port: int) -> None:
    """해당 포트를 LISTEN 중인 프로세스를 종료(직전 arm/worker의 잔여 서버 제거).

    다중 arm 실행 시 이전 arm의 서버가 포트를 점유해 다음 arm 채점을 오염시키는 것을 방지.
    """
    try:
        out = subprocess.run(f"lsof -ti tcp:{port} -sTCP:LISTEN", shell=True,
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:  # noqa: BLE001
        return
    for pid in out.split():
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError):
            pass


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
    _free_port(port)  # worker/직전 arm의 잔여 서버 제거 후 깨끗이 부팅
    env = {**os.environ, "PORT": str(port)}
    subprocess.run("npm install", shell=True, cwd=workdir, env=env,
                   capture_output=True, text=True, timeout=300)
    proc = subprocess.Popen(boot_cmd, shell=True, cwd=workdir, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        if not _wait_health(port, boot_timeout):
            return fail
        report_path = os.path.join(workdir, "newman-report.json")
        subprocess.run(
            f"newman run {shlex.quote(collection_path)} --reporters json "
            f"--reporter-json-export {report_path} "
            f"--env-var APIURL=http://localhost:{port}/api",
            shell=True, capture_output=True, text=True, timeout=300,
        )
        report = _load_report(report_path)
        if report is None:
            return {"server_ok": True, "total": 0, "passed": 0,
                     "failures": ["newman produced no report"]}
        out = parse_newman_json(report)
        out["server_ok"] = True
        return out
    finally:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        _free_port(port)  # 채점 후 포트 확실히 해제(다음 arm 대비)
