"""Unit and integration tests for Phase 8: Report Agent and Human Sign-Off Gate.

Validates:
1. Deterministic formatting of 7-section Audit Memorandum from verified data.
2. Accurate classification: Confirmed findings in main report, needs-evidence in separate section, dropped in appendix.
3. Strict numerical fidelity: Exact financial amounts and entry IDs match tool/profile outputs.
4. Overlapping exposure disclaimer is present.
5. Memorandum file writing with status validation and overwrite protection (cannot downgrade FINAL to DRAFT).
6. Human approval gate:
   - APPROVE flips DRAFT to FINAL with auditable sign-off block.
   - REJECT and REQUEST_CHANGES preserve DRAFT.
   - Invalid decisions rejected.
   - Report agent cannot self-approve or finalize automatically.
7. Intake fail-closed guard: FAILED intake halts report drafting.
8. 100% offline testing with zero Gemini API calls.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions import Session

from auditpilot.agents.pipeline import SpecialistGateAgent, specialist_gate
from auditpilot.agents.report import ReportAgent, report_agent
from auditpilot.tools.report_tools import (
    format_audit_memo,
    sign_off_memo,
    write_audit_memo,
)


# =====================================================================
# Fixtures and Sample Data
# =====================================================================

@pytest.fixture
def sample_data_profile() -> dict:
    return {
        "status": "PASSED_WITH_VARIANCE",
        "row_count": 6000,
        "column_count": 11,
        "total_debit_inr": 171175194.18,
        "total_credit_inr": 171175194.18,
        "is_balanced": True,
        "start_date": "2025-04-01",
        "end_date": "2026-03-31",
        "trial_balance_reconciled": False,
        "trial_balance_gap_inr": 125000.0,
        "flagged_ids": ["JE-2025-2767"],
        "notes": "Ledger verified. Trial balance discrepancy detected on Account 6020.",
    }


@pytest.fixture
def sample_ranked_findings() -> dict:
    return {
        "findings": [
            {
                "id": "FIND-001",
                "category": "compliance",
                "title": "Segregation of Duties Self-Approval",
                "entry_ids": ["JE-2025-0101", "JE-2025-0102"],
                "evidence": ["Maker EMP-16 posted and approved entry"],
                "amount_at_risk_inr": 85000.0,
                "likelihood": 4,
                "impact": 3,
                "score": 12,
                "rationale": "Direct breach of SOP Clause 3.1",
                "status": "confirmed",
                "review_reason": "Verified against employee master: maker equals checker.",
            },
            {
                "id": "FIND-002",
                "category": "anomaly",
                "title": "Potential Split Payment Structuring",
                "entry_ids": ["JE-2025-0201", "JE-2025-0202"],
                "evidence": ["2 disbursements of Rs 48,000 within 24 hours"],
                "amount_at_risk_inr": 96000.0,
                "likelihood": 3,
                "impact": 3,
                "score": 9,
                "rationale": "Near-threshold payments to same vendor",
                "status": "needs_evidence",
                "review_reason": "Requires purchase orders and requisitions to verify business purpose.",
            },
            {
                "id": "FIND-003",
                "category": "vendor",
                "title": "Nonexistent Journal Entry Claim",
                "entry_ids": ["INVALID-JE-9999"],
                "evidence": ["Sample unverified finding"],
                "amount_at_risk_inr": 50000.0,
                "likelihood": 1,
                "impact": 1,
                "score": 1,
                "rationale": "Test invalid finding",
                "status": "dropped",
                "review_reason": "Journal entry ID verification failed: 1 supplied journal entry ID(s) do not exist.",
            },
        ],
        "total_findings": 3,
        "total_amount_at_risk_inr": 231000.0,
    }


# =====================================================================
# 1. Deterministic Format Tests
# =====================================================================

def test_format_audit_memo_contains_all_sections(sample_data_profile, sample_ranked_findings):
    """Verify that format_audit_memo produces the full structured 7-section memorandum."""
    memo = format_audit_memo(sample_data_profile, sample_ranked_findings, status="DRAFT")

    assert "# AUDIT MEMORANDUM" in memo
    assert "**Status: DRAFT** (Awaiting Partner Sign-Off)" in memo
    assert "## 1. Scope and Data" in memo
    assert "## 2. Executive Summary" in memo
    assert "## 3. Ranked Findings (Confirmed)" in memo
    assert "## 4. Findings Requiring Additional Evidence" in memo
    assert "## 5. Recommended Actions for Management" in memo
    assert "## 6. Scope Limitations" in memo
    assert "## 7. Appendix: Dropped Findings and Review Justification" in memo
    assert "## 8. Partner Sign-Off Record" in memo


def test_format_audit_memo_numerical_fidelity(sample_data_profile, sample_ranked_findings):
    """Verify exact financial numbers and entry IDs from data profile and findings appear verbatim."""
    memo = format_audit_memo(sample_data_profile, sample_ranked_findings, status="DRAFT")

    # Scope numbers
    assert "6,000" in memo
    assert "171,175,194.18" in memo
    assert "125,000.00" in memo
    assert "JE-2025-2767" in memo

    # Confirmed finding numbers
    assert "FIND-001" in memo
    assert "85,000.00" in memo
    assert "JE-2025-0101" in memo
    assert "JE-2025-0102" in memo

    # Needs-evidence numbers
    assert "FIND-020" not in memo
    assert "FIND-002" in memo
    assert "JE-2025-0201" in memo

    # Dropped finding numbers
    assert "FIND-003" in memo
    assert "INVALID-JE-9999" in memo


def test_format_audit_memo_classifies_findings_correctly(sample_data_profile, sample_ranked_findings):
    """Verify confirmed findings are in Section 3, needs_evidence in Section 4, dropped in Section 7."""
    memo = format_audit_memo(sample_data_profile, sample_ranked_findings, status="DRAFT")

    sec3_part = memo.split("## 3. Ranked Findings (Confirmed)")[1].split("## 4. Findings Requiring Additional Evidence")[0]
    sec4_part = memo.split("## 4. Findings Requiring Additional Evidence")[1].split("## 5. Recommended Actions for Management")[0]
    sec7_part = memo.split("## 7. Appendix: Dropped Findings and Review Justification")[1].split("## 8. Partner Sign-Off Record")[0]

    # FIND-001 is confirmed -> must be in Section 3
    assert "FIND-001" in sec3_part
    assert "FIND-002" not in sec3_part
    assert "FIND-003" not in sec3_part

    # FIND-002 is needs_evidence -> must be in Section 4
    assert "FIND-002" in sec4_part
    assert "FIND-001" not in sec4_part
    assert "FIND-003" not in sec4_part

    # FIND-003 is dropped -> must be in Section 7 Appendix
    assert "FIND-003" in sec7_part
    assert "FIND-001" not in sec7_part
    assert "FIND-002" not in sec7_part
    assert "verification failed" in sec7_part.lower()


def test_format_audit_memo_includes_overlapping_exposure_disclaimer(sample_data_profile, sample_ranked_findings):
    """Verify that the memorandum explicitly warns against summing overlapping category exposures."""
    memo = format_audit_memo(sample_data_profile, sample_ranked_findings, status="DRAFT")

    assert "Note on Financial Exposure" in memo
    assert "Category-level financial exposures can overlap" in memo
    assert "must not be interpreted as unique additive company losses" in memo


def test_format_audit_memo_rejects_invalid_status(sample_data_profile, sample_ranked_findings):
    """Verify format_audit_memo raises ValueError on invalid status string."""
    with pytest.raises(ValueError, match="Invalid status"):
        format_audit_memo(sample_data_profile, sample_ranked_findings, status="APPROVED")


# =====================================================================
# 2. File Writing Tests
# =====================================================================

def test_write_audit_memo_creates_file(tmp_path: Path):
    """Verify write_audit_memo writes the file and returns uniform result dict."""
    target_file = tmp_path / "docs" / "test_memo.md"
    content = "# AUDIT MEMORANDUM\nStatus: DRAFT\nSample Content"

    res = write_audit_memo(markdown_content=content, status="DRAFT", output_path=str(target_file))

    assert res["test"] == "write_audit_memo"
    assert res["status"] == "DRAFT"
    assert target_file.is_file()
    assert target_file.read_text(encoding="utf-8").strip() == content


def test_write_audit_memo_rejects_invalid_status(tmp_path: Path):
    """Verify write_audit_memo raises ValueError on invalid status."""
    target_file = tmp_path / "docs" / "invalid_memo.md"
    with pytest.raises(ValueError, match="Invalid status"):
        write_audit_memo(markdown_content="Text", status="PENDING", output_path=str(target_file))


def test_write_audit_memo_prevents_downgrading_final_to_draft(tmp_path: Path):
    """Security check: Cannot overwrite or downgrade an already approved FINAL report to DRAFT."""
    target_file = tmp_path / "docs" / "final_memo.md"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("# AUDIT MEMORANDUM\n**Status: FINAL**\nApproved content.", encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot overwrite or downgrade a FINAL"):
        write_audit_memo(markdown_content="New Draft", status="DRAFT", output_path=str(target_file))


# =====================================================================
# 3. Human Sign-Off Gate Tests
# =====================================================================

def test_sign_off_memo_approve_flips_draft_to_final(tmp_path: Path):
    """Verify human approval flips DRAFT to FINAL and appends immutable sign-off block."""
    memo_file = tmp_path / "docs" / "audit_memo.md"
    memo_file.parent.mkdir(parents=True, exist_ok=True)
    initial_content = (
        "---\n"
        "# AUDIT MEMORANDUM\n"
        "**Status: DRAFT** (Awaiting Partner Sign-Off)\n"
        "---\n"
        "Findings details...\n"
    )
    memo_file.write_text(initial_content, encoding="utf-8")

    res = sign_off_memo(
        decision="APPROVE",
        reviewer_name="Sneha Kulkarni, Partner",
        comments="Findings verified against supporting schedules.",
        memo_path=str(memo_file),
        timestamp="2026-11-20T12:00:00Z",
    )

    assert res["test"] == "sign_off_memo"
    assert res["decision"] == "APPROVE"
    assert res["previous_status"] == "DRAFT"
    assert res["status"] == "FINAL"
    assert res["reviewer_name"] == "Sneha Kulkarni, Partner"
    assert res["timestamp"] == "2026-11-20T12:00:00Z"

    updated = memo_file.read_text(encoding="utf-8")
    assert "**Status: FINAL**" in updated
    assert "(Signed Off by Audit Partner)" in updated
    assert "Sneha Kulkarni, Partner" in updated
    assert "2026-11-20T12:00:00Z" in updated
    assert "Findings verified against supporting schedules." in updated


def test_sign_off_memo_reject_preserves_draft(tmp_path: Path):
    """Verify REJECT preserves DRAFT status and records review feedback."""
    memo_file = tmp_path / "docs" / "audit_memo.md"
    memo_file.parent.mkdir(parents=True, exist_ok=True)
    memo_file.write_text("# AUDIT MEMORANDUM\n**Status: DRAFT**\n", encoding="utf-8")

    res = sign_off_memo(
        decision="REJECT",
        reviewer_name="Rajesh Sharma, Senior Partner",
        comments="Incomplete evidence for vendor findings.",
        memo_path=str(memo_file),
        timestamp="2026-11-20T12:30:00Z",
    )

    assert res["decision"] == "REJECT"
    assert res["status"] == "DRAFT"

    content = memo_file.read_text(encoding="utf-8")
    assert "**Status: DRAFT**" in content
    assert "Status: FINAL" not in content
    assert "Incomplete evidence for vendor findings." in content


def test_sign_off_memo_request_changes_preserves_draft(tmp_path: Path):
    """Verify REQUEST_CHANGES preserves DRAFT status and records review feedback."""
    memo_file = tmp_path / "docs" / "audit_memo.md"
    memo_file.parent.mkdir(parents=True, exist_ok=True)
    memo_file.write_text("# AUDIT MEMORANDUM\n**Status: DRAFT**\n", encoding="utf-8")

    res = sign_off_memo(
        decision="REQUEST_CHANGES",
        reviewer_name="Audit Partner",
        comments="Please clarify exposure overlap note.",
        memo_path=str(memo_file),
    )

    assert res["decision"] == "REQUEST_CHANGES"
    assert res["status"] == "DRAFT"

    content = memo_file.read_text(encoding="utf-8")
    assert "**Status: DRAFT**" in content
    assert "Status: FINAL" not in content
    assert "Please clarify exposure overlap note." in content


def test_sign_off_memo_rejects_invalid_decision(tmp_path: Path):
    """Verify sign_off_memo raises ValueError on invalid decision string."""
    memo_file = tmp_path / "docs" / "audit_memo.md"
    memo_file.parent.mkdir(parents=True, exist_ok=True)
    memo_file.write_text("# AUDIT MEMORANDUM\n**Status: DRAFT**\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid sign-off decision"):
        sign_off_memo(decision="MAYBE", memo_path=str(memo_file))


def test_sign_off_memo_missing_file_error():
    """Verify sign_off_memo raises FileNotFoundError when memo does not exist."""
    with pytest.raises(FileNotFoundError):
        sign_off_memo(decision="APPROVE", memo_path="nonexistent/path/memo.md")


def test_report_agent_cannot_self_approve():
    """Security check: report_agent must only have write_audit_memo tool and cannot approve."""
    tool_names = [tool.__name__ for tool in report_agent.tools]

    assert "write_audit_memo" in tool_names
    # sign_off_memo must NOT be exposed as an automated agent tool to prevent self-approval
    assert "sign_off_memo" not in tool_names


# =====================================================================
# 4. ReportAgent and Pipeline Guard Integration Tests
# =====================================================================

def test_report_agent_execution_creates_draft(sample_data_profile, sample_ranked_findings):
    """Verify report_agent runs deterministically and produces docs/audit_memo.md in DRAFT status."""
    async def _test():
        session = Session(
            id="report_sess_001",
            app_name="auditpilot",
            user_id="test_user",
            state={
                "data_profile": sample_data_profile,
                "ranked_findings": sample_ranked_findings,
            },
        )
        ctx = MagicMock(spec=InvocationContext)
        ctx.session = session
        ctx.invocation_id = "inv_rep_001"
        ctx.branch = "main"

        events = []
        async for event in report_agent._run_async_impl(ctx):
            events.append(event)

        assert len(events) == 1
        event = events[0]
        assert event.actions.state_delta["audit_memo_status"] == "DRAFT"
        assert event.actions.state_delta["audit_memo_path"] == "docs/audit_memo.md"

        memo_file = Path("docs/audit_memo.md")
        assert memo_file.is_file()
        content = memo_file.read_text(encoding="utf-8")
        assert "**Status: DRAFT**" in content
        assert "FIND-001" in content
        assert "FIND-002" in content
        assert "FIND-003" in content

    asyncio.run(_test())


def test_report_agent_halts_on_failed_intake():
    """Verify report_agent halts and does not generate a report if data intake failed."""
    async def _test():
        session = Session(
            id="report_sess_fail",
            app_name="auditpilot",
            user_id="test_user",
            state={
                "data_profile": {
                    "status": "FAILED",
                    "failure_reasons": ["Ledger file not found."],
                },
                "ranked_findings": {"findings": []},
            },
        )
        ctx = MagicMock(spec=InvocationContext)
        ctx.session = session
        ctx.invocation_id = "inv_rep_fail"
        ctx.branch = "main"

        events = []
        async for event in report_agent._run_async_impl(ctx):
            events.append(event)

        assert len(events) == 1
        event = events[0]
        # Must not set audit_memo_status in state_delta
        assert "audit_memo_status" not in (event.actions.state_delta or {})
        text = event.content.parts[0].text
        assert "Report generation halted" in text
        assert "FAILED" in text

    asyncio.run(_test())


def test_report_agent_registration():
    """Verify report_agent name, description, and output key."""
    assert report_agent.name == "report_agent"
    assert report_agent.output_key == "audit_memo_output"
    assert "Audit Memorandum" in report_agent.description
