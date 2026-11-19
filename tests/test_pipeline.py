from auditpilot.agents.policy import policy_agent
from auditpilot.agents.pipeline import specialists
import pytest

from auditpilot.agents.pipeline import intake_allows_specialists


@pytest.mark.parametrize(
    "status, expected",
    [
        ("PASSED", True),
        ("PASSED_WITH_VARIANCE", True),
        ("FAILED", False),
        ("MISSING", False),
        ("UNKNOWN", False),
    ],
)
def test_intake_allows_specialists(status, expected):
    profile = {"status": status}

    assert intake_allows_specialists(profile) is expected


def test_intake_allows_specialists_with_missing_profile():
    assert intake_allows_specialists({}) is False
    assert intake_allows_specialists(None) is False

def test_policy_agent_registration():
    assert policy_agent.name == "policy_agent"
    assert policy_agent.output_key == "policy_findings"


def test_policy_agent_tools():
    tool_names = [tool.__name__ for tool in policy_agent.tools]

    assert "retrieve_policy" in tool_names
    assert "check_approval_limits" in tool_names


def test_specialists_registration():
    specialist_names = [agent.name for agent in specialists.sub_agents]

    assert specialist_names == [
        "anomaly_agent",
        "vendor_agent",
        "ratio_agent",
    ]
