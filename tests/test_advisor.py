from harness.advisor import ADVISOR_SYSTEM


def test_advisor_system_forbids_tools_and_wants_numbered_steps():
    s = ADVISOR_SYSTEM.lower()
    assert "no tools" in s
    assert "numbered" in s
    assert "strategy" in s
