import json

from harness.grade import _load_report, parse_newman_json


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


def test_load_report_missing_returns_none(tmp_path):
    assert _load_report(str(tmp_path / "nope.json")) is None


def test_load_report_valid(tmp_path):
    path = tmp_path / "report.json"
    data = {"run": {"stats": {"assertions": {"total": 1, "failed": 0}}, "failures": []}}
    path.write_text(json.dumps(data))
    assert _load_report(str(path)) == data
