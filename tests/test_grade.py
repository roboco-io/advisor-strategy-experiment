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
