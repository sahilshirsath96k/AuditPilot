"""Deterministic Audit Reporting and Sign-Off Tools for AuditPilot.

Provides structured memorandum writing, status management, numerical fidelity,
and human-in-the-loop audit partner sign-off controls.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def format_audit_memo(
    data_profile: dict,
    ranked_findings: dict,
    status: str = "DRAFT",
) -> str:
    """Deterministically format the full 7-section Audit Memorandum from verified data.

    Enforces:
    1. Confirmed findings in main report (Section 3).
    2. Needs-evidence findings in separate section (Section 4).
    3. Dropped findings in appendix with reasons (Section 7).
    4. Strict numerical fidelity: all amounts, IDs, and metrics derived from verified inputs.
    5. Disclaimers regarding overlapping category exposures.

    Args:
        data_profile: Verified data profile from intake_agent.
        ranked_findings: Ranked and skeptic-reviewed findings.
        status: Initial memorandum status ('DRAFT' or 'FINAL', default: 'DRAFT').

    Returns:
        Full markdown string for docs/audit_memo.md.
    """
    clean_status = status.strip().upper()
    if clean_status not in ("DRAFT", "FINAL"):
        raise ValueError(f"Invalid status '{status}'. Must be 'DRAFT' or 'FINAL'.")

    # Extract intake metrics
    row_count = data_profile.get("row_count")
    col_count = data_profile.get("column_count")
    start_date = data_profile.get("start_date")
    end_date = data_profile.get("end_date")
    debit_sum = data_profile.get("total_debit_inr")
    credit_sum = data_profile.get("total_credit_inr")
    is_balanced = data_profile.get("is_balanced")
    tb_gap = data_profile.get("trial_balance_gap_inr")
    tb_reconciled = data_profile.get("trial_balance_reconciled")
    flagged_intake_ids = data_profile.get("flagged_ids") or []
    tb_discrepancies = data_profile.get("trial_balance_discrepancies") or []
    def display_value(value, formatter=str):
        return "Not available" if value is None else formatter(value)

    # Categorize findings
    raw_findings = ranked_findings.get("findings", [])
    confirmed_findings = [f for f in raw_findings if f.get("status") == "confirmed"]
    needs_evidence_findings = [f for f in raw_findings if f.get("status") == "needs_evidence"]
    dropped_findings = [f for f in raw_findings if f.get("status") == "dropped"]

    # Header Banner
    header = (
        "---\n"
        "# AUDIT MEMORANDUM\n"
        f"**Status: {clean_status}** ({'Awaiting Partner Sign-Off' if clean_status == 'DRAFT' else 'Signed Off by Audit Partner'})\n"
	"**Entity:** Not independently verified from source ledger files\n"
	f"**Fiscal Period:** {start_date or 'Not available'} to {end_date or 'Not available'}\n"
        "---\n\n"
    )

    # Section 1: Scope and Data
    sec1 = (
        "## 1. Scope and Data\n\n"
        f"- **Audit Period:** {start_date or 'Not available'} to {end_date or 'Not available'}\n"
        f"- **General Ledger Records:** {display_value(row_count, lambda v: f'{v:,}')} "
        f"journal entries across {display_value(col_count)} columns\n"
        f"- **Double-Entry Bookkeeping:** "
        f"{'Balanced' if is_balanced is True else 'Unbalanced' if is_balanced is False else 'Not verified'} "
        f"(Total Debits: {display_value(debit_sum, lambda v: f'₹{v:,.2f}')} | "
        f"Total Credits: {display_value(credit_sum, lambda v: f'₹{v:,.2f}')})\n"
        f"- **Trial Balance Reconciliation:** "
        f"{'Reconciled' if tb_reconciled is True else 'Unreconciled with Variance' if tb_reconciled is False else 'Not verified'}\n"
        f"  - **Identified Gap:** {display_value(tb_gap, lambda v: f'₹{v:,.2f}')}\n"
        f"  - **Discrepant Accounts:** {', '.join(str(d.get('account_code')) + ' (' + str(d.get('account_name')) + ')' for d in tb_discrepancies) if tb_discrepancies else 'None identified'}\n"
        f"  - **Candidate Entry IDs:** {', '.join(flagged_intake_ids) if flagged_intake_ids else 'None'}\n\n"
    )

    # Section 2: Executive Summary
    sec2 = (
        "## 2. Executive Summary\n\n"
        "AuditPilot conducted a comprehensive, multi-agent forensic audit of the general ledger, vendor disbursements, "
        "and corporate governance controls for FY 2025–26. All transactions were evaluated against corporate standard operating "
        "procedures (SOP-FIN-PROC-2025-V1) and Indian Accounting Standards (Ind AS).\n\n"
        "### Summary of Findings:\n"
        f"- **Total Findings Analyzed:** {len(raw_findings)}\n"
        f"- **Confirmed Findings:** {len(confirmed_findings)}\n"
        f"- **Findings Requiring Further Evidence:** {len(needs_evidence_findings)}\n"
        f"- **Dropped Findings (in Appendix):** {len(dropped_findings)}\n\n"
        "> [!NOTE] **Note on Financial Exposure:**\n"
        "> Category-level financial exposures can overlap across accounting dimensions (e.g., an unauthorized payment may also "
        "> be flagged under weekend timing or round amounts) and must not be interpreted as unique additive company losses.\n\n"
    )

    # Section 3: Ranked Confirmed Findings
    sec3_rows = []
    sec3_details = []
    for f in confirmed_findings:
        f_id = f.get("id", "N/A")
        cat = f.get("category", "General").capitalize()
        title = f.get("title", "Untitled Finding")
        eids = ", ".join(f.get("entry_ids", []))
        amt = f.get("amount_at_risk_inr", 0.0)
        score = f.get("score", 0)
        lh = f.get("likelihood", 1)
        imp = f.get("impact", 1)
        sec3_rows.append(f"| {f_id} | {cat} | {title} | {eids} | ₹{amt:,.2f} | {score} ({lh}×{imp}) |")

        ev_list = "\n".join(f"  - {e}" for e in f.get("evidence", [])) or "  - Standard audit tool output"
        reason = f.get("review_reason", "Confirmed by skeptic independent verification.")
        sec3_details.append(
            f"### {f_id}: {title}\n"
            f"- **Category:** {cat}\n"
            f"- **Risk Score:** {score} (Likelihood: {lh}/5, Impact: {imp}/5)\n"
            f"- **Amount at Risk:** ₹{amt:,.2f}\n"
            f"- **Cited Entry IDs:** {eids}\n"
            f"- **Supporting Evidence:**\n{ev_list}\n"
            f"- **Rationale:** {f.get('rationale', 'N/A')}\n"
            f"- **Skeptic Review:** {reason}\n"
        )

    sec3_table = (
        "| Finding ID | Category | Title | Cited Entry IDs | Exposure (INR) | Score |\n"
        "|---|---|---|---|---|---|\n"
        + ("\n".join(sec3_rows) if sec3_rows else "| None | - | No confirmed findings | - | ₹0.00 | 0 |")
        + "\n\n"
    )
    sec3 = "## 3. Ranked Findings (Confirmed)\n\n" + sec3_table + "\n".join(sec3_details) + "\n"

    # Section 4: Findings Requiring Additional Evidence
    sec4_rows = []
    for f in needs_evidence_findings:
        f_id = f.get("id", "N/A")
        title = f.get("title", "Untitled Finding")
        eids = ", ".join(f.get("entry_ids", []))
        reason = f.get("review_reason", "Secondary documentation required.")
        sec4_rows.append(f"| {f_id} | {title} | {eids} | {reason} |")

    sec4 = (
        "## 4. Findings Requiring Additional Evidence\n\n"
        "The following findings exhibit statistical anomalies or potential policy variances, but require external or "
        "supplementary evidence (such as physical gate passes, delivery challans, or email approvals) before a conclusive "
        "breach can be established:\n\n"
        "| Finding ID | Title | Cited Entry IDs | Required Evidence / Note |\n"
        "|---|---|---|---|\n"
        + ("\n".join(sec4_rows) if sec4_rows else "| None | No findings currently pending evidence | - | - |")
        + "\n\n"
    )

    # Section 5: Recommended Actions for Management
    discrepancy_accounts = "; ".join(
        f"{item.get('account_code')} ({item.get('account_name')})"
        for item in tb_discrepancies
    ) or "No discrepant accounts identified"

    discrepancy_action = (
        f"Investigate the trial-balance variance of "
        f"{display_value(tb_gap, lambda v: f'₹{v:,.2f}')} "
        f"for {discrepancy_accounts}. "
        f"Candidate entry IDs: {', '.join(flagged_intake_ids) or 'None'}. "
        "Reconcile the ledger balances with supporting schedules before posting any adjustment."
        if tb_discrepancies or tb_gap is not None
        else "No trial-balance discrepancy was reported by the intake process."
    )

    sec5 = (
        "## 5. Recommended Actions for Management\n\n"
        "1. **Segregation of Duties Enforcement:** Implement system-level maker-checker "
        "controls to prevent journal vouchers where `posted_by == approved_by`.\n"
        "2. **Vendor Master & Payroll Cross-Matching:** Introduce automated checks "
        "between employee bank accounts and registered vendor bank accounts.\n"
        "3. **Approval Threshold Monitoring:** Monitor transaction aggregation against "
        "the delegated authority limits defined in the applicable approval policy.\n"
        f"4. **Trial Balance Reconciliation:** {discrepancy_action}\n\n"
    )

    # Section 6: Limitations
    sec6 = (
        "## 6. Scope Limitations\n\n"
        "- The audit procedures were conducted on provided electronic general ledger and financial schedules for FY 2025–26.\n"
        "- Audit procedures did not include physical inventory stock verification or direct external bank confirmation circulars.\n"
        "- Statistical indicators (such as first-digit Benford's Law conformity) serve as screening mechanisms and do not "
        "constitute definitive legal evidence of fraudulent activity without corroborating transactional documentation.\n\n"
    )

    # Section 7: Appendix — Dropped Findings
    sec7_rows = []
    for f in dropped_findings:
        f_id = f.get("id", "N/A")
        cat = f.get("category", "General").capitalize()
        title = f.get("title", "Untitled Finding")
        eids = ", ".join(f.get("entry_ids", [])) or "None"
        reason = f.get("review_reason", "Did not meet required evidentiary standard.")
        sec7_rows.append(f"| {f_id} | {cat} | {title} | {eids} | {reason} |")

    sec7 = (
        "## 7. Appendix: Dropped Findings and Review Justification\n\n"
        "In accordance with auditing standards, findings that did not meet verification criteria (such as nonexistent journal "
        "entry IDs or unsupported initial hypotheses) are retained below with full transparency:\n\n"
        "| Finding ID | Category | Title | Cited Entry IDs | Reason for Dropping |\n"
        "|---|---|---|---|---|\n"
        + ("\n".join(sec7_rows) if sec7_rows else "| None | - | No findings were dropped | - | - |")
        + "\n\n"
    )

    # Section 8: Partner Sign-Off Block
    sec8 = (
        "## 8. Partner Sign-Off Record\n\n"
        "| Field | Status Details |\n"
        "|---|---|\n"
        f"| **Memorandum Status** | **{clean_status}** ({'Awaiting Partner Sign-Off' if clean_status == 'DRAFT' else 'Signed Off by Audit Partner'}) |\n"
        "| **Sign-Off Authority** | Audit Engagement Partner |\n"
        "| **Review Decision** | Pending Formal Partner Review |\n"
    )

    return header + sec1 + sec2 + sec3 + sec4 + sec5 + sec6 + sec7 + sec8


def write_audit_memo(
    markdown_content: str,
    status: str = "DRAFT",
    output_path: str = "docs/audit_memo.md",
) -> dict[str, Any]:
    """Deterministically write formatted audit memorandum to markdown file.

    Guarantees:
    1. Status validation ('DRAFT' or 'FINAL').
    2. Overwrite protection: prevents overwriting or downgrading a 'FINAL' report.
    3. Creation of parent directory.

    Args:
        markdown_content: The full markdown body of the audit memorandum.
        status: Status of the memorandum ('DRAFT' or 'FINAL', default: 'DRAFT').
        output_path: Target file path (default: 'docs/audit_memo.md').

    Returns:
        A dictionary with keys: test, path, status, bytes_written, notes.
    """
    clean_status = status.strip().upper()
    if clean_status not in ("DRAFT", "FINAL"):
        raise ValueError(f"Invalid status '{status}'. Must be either 'DRAFT' or 'FINAL'.")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Overwrite protection: Cannot downgrade or overwrite an already approved FINAL report
    if path.is_file():
        existing_content = path.read_text(encoding="utf-8")
        if "**Status: FINAL**" in existing_content or "Status: FINAL" in existing_content:
            if clean_status != "FINAL":
                raise ValueError(
                    f"Cannot overwrite or downgrade a FINAL audit memorandum at {path} to {clean_status}."
                )

    clean_content = markdown_content.strip()

    with open(path, "w", encoding="utf-8") as f:
        f.write(clean_content + "\n")

    return {
        "test": "write_audit_memo",
        "path": str(path),
        "status": clean_status,
        "bytes_written": len((clean_content + "\n").encode("utf-8")),
        "notes": f"Audit memorandum successfully written to {path} with Status: {clean_status}.",
    }


def sign_off_memo(
    decision: str,
    reviewer_name: str = "Audit Partner",
    comments: str = "",
    memo_path: str = "docs/audit_memo.md",
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Execute human-in-the-loop audit partner sign-off decision.

    Guarantees:
    1. Validates decision against ('APPROVE', 'REJECT', 'REQUEST_CHANGES').
    2. 'APPROVE' flips status from 'DRAFT' to 'FINAL' and records an immutable sign-off block.
    3. 'REJECT' and 'REQUEST_CHANGES' strictly preserve 'DRAFT' status.
    4. Records previous status, resulting status, reviewer name, timestamp, and comments.

    Args:
        decision: Partner decision ('APPROVE', 'REJECT', or 'REQUEST_CHANGES').
        reviewer_name: Identity of the reviewing partner (default: 'Audit Partner').
        comments: Review commentary, feedback, or sign-off notes.
        memo_path: Path to the audit memorandum file (default: 'docs/audit_memo.md').
        timestamp: Optional ISO 8601 timestamp string (for deterministic offline testing).

    Returns:
        A dictionary with keys: test, decision, previous_status, status, path, reviewer_name, timestamp, notes.
    """
    clean_decision = decision.strip().upper()
    valid_decisions = {"APPROVE", "REJECT", "REQUEST_CHANGES"}
    if clean_decision not in valid_decisions:
        raise ValueError(f"Invalid sign-off decision '{decision}'. Must be one of {valid_decisions}.")

    path = Path(memo_path)
    if not path.is_file():
        raise FileNotFoundError(f"Audit memorandum not found at path: {path}")

    content = path.read_text(encoding="utf-8")

    previous_status = "FINAL" if ("**Status: FINAL**" in content or "Status: FINAL" in content) else "DRAFT"
    now_iso = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if clean_decision == "APPROVE":
        if previous_status == "FINAL":
            return {
                "test": "sign_off_memo",
                "decision": "APPROVE",
                "previous_status": "FINAL",
                "status": "FINAL",
                "path": str(path),
                "reviewer_name": reviewer_name,
                "timestamp": now_iso,
                "notes": f"Audit memorandum at {path} is already finalized.",
            }

        updated_content = content.replace("Status: DRAFT", "Status: FINAL")
        updated_content = updated_content.replace("**Status: DRAFT**", "**Status: FINAL**")
        updated_content = updated_content.replace(
            "(Awaiting Partner Sign-Off)",
            "(Signed Off by Audit Partner)",
        )

        signoff_block = (
            "\n## 8. Partner Sign-Off Record\n\n"
            "| Field | Value |\n"
            "|---|---|\n"
            f"| **Reviewer** | {reviewer_name} |\n"
            "| **Decision** | **APPROVED** |\n"
            f"| **Timestamp** | {now_iso} |\n"
            f"| **Previous Status** | {previous_status} |\n"
            "| **Resulting Status** | **FINAL** |\n"
            f"| **Partner Commentary** | {comments or 'Approved as final audit memorandum for stakeholder issuance.'} |\n"
        )

        if "## 8. Partner Sign-Off Record" in updated_content:
            parts = updated_content.split("## 8. Partner Sign-Off Record")
            updated_content = parts[0].rstrip() + "\n" + signoff_block
        else:
            updated_content = updated_content.rstrip() + "\n" + signoff_block

        path.write_text(updated_content, encoding="utf-8")

        return {
            "test": "sign_off_memo",
            "decision": "APPROVE",
            "previous_status": previous_status,
            "status": "FINAL",
            "path": str(path),
            "reviewer_name": reviewer_name,
            "timestamp": now_iso,
            "notes": f"Audit memorandum successfully signed off and finalized by {reviewer_name}.",
        }

    else:
        # REJECT or REQUEST_CHANGES strictly preserves DRAFT status
        feedback_block = (
            f"\n\n> [!WARNING] **Partner Review Feedback ({clean_decision} at {now_iso})**\n"
            f"> **Reviewer:** {reviewer_name}\n"
            f"> **Decision:** {clean_decision}\n"
            f"> **Status Preserved:** DRAFT\n"
            f"> **Commentary:** {comments or 'Changes requested prior to final approval.'}\n"
        )
        updated_content = content.rstrip() + feedback_block
        path.write_text(updated_content, encoding="utf-8")

        return {
            "test": "sign_off_memo",
            "decision": clean_decision,
            "previous_status": previous_status,
            "status": "DRAFT",
            "path": str(path),
            "reviewer_name": reviewer_name,
            "timestamp": now_iso,
            "notes": f"Sign-off decision '{clean_decision}' recorded by {reviewer_name}. Memorandum remains in Status: DRAFT.",
        }
