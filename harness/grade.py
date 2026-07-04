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
