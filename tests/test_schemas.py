
import pytest
from pydantic import ValidationError

from auditpilot.schemas import Finding


def test_finding_creation():
    finding = Finding(
        id="F-001",
        category="anomaly",
        title="Duplicate payment",
        entry_ids=["JE-001"],
        amount_at_risk_inr=50000,
        likelihood=4,
        impact=3,
        score=12,
        rationale="Duplicate payment detected.",
    )

    assert finding.id == "F-001"
    assert finding.amount_at_risk_inr == 50000
    assert finding.score == 12


def test_finding_default_lists():
    finding = Finding(
        id="F-002",
        category="vendor",
        title="Vendor issue",
        entry_ids=["JE-002"],
        likelihood=3,
        impact=2,
        rationale="Vendor verification concern.",
    )

    assert finding.evidence == []
    assert finding.amount_at_risk_inr == 0.0
    assert finding.status == "pending"


def test_finding_rejects_negative_amount():
    with pytest.raises(ValidationError):
        Finding(
            id="F-003",
            category="anomaly",
            title="Invalid amount",
            entry_ids=["JE-003"],
            amount_at_risk_inr=-100,
            likelihood=2,
            impact=2,
            rationale="Invalid test.",
        )


def test_finding_rejects_invalid_score():
    with pytest.raises(ValidationError):
        Finding(
            id="F-004",
            category="anomaly",
            title="Invalid score",
            entry_ids=["JE-004"],
            likelihood=2,
            impact=2,
            score=30,
            rationale="Score exceeds maximum.",
        )


def test_finding_rejects_invalid_likelihood():
    with pytest.raises(ValidationError):
        Finding(
            id="F-005",
            category="anomaly",
            title="Invalid likelihood",
            entry_ids=["JE-005"],
            likelihood=6,
            impact=2,
            rationale="Likelihood exceeds maximum.",
        )
