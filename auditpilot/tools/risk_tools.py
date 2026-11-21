
"""Deterministic risk calculation and finding aggregation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd

from auditpilot.schemas import Finding
from auditpilot.tools.anomaly_tools import (
    benford_test,
    find_duplicates,
    find_split_payments,
    find_weekend_round,
)
from auditpilot.tools.compliance_tools import (
    check_approval_limits,
    vendor_bank_overlap,
)
from auditpilot.tools.ratio_tools import ratio_table


def _safe_amount(value: Any) -> float:
    """Return a finite, non-negative monetary amount."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return 0.0

    if not pd.notna(amount) or amount < 0:
        return 0.0

    return round(amount, 2)


def _make_finding(
    *,
    finding_id: str,
    category: str,
    title: str,
    entry_ids: list[str],
    evidence: list[str],
    amount: float,
    likelihood: int,
    impact: int,
    rationale: str,
) -> Finding:
    """Construct a finding with a deterministically calculated score."""
    likelihood = max(1, min(5, int(likelihood)))
    impact = max(1, min(5, int(impact)))

    return Finding(
        id=finding_id,
        category=category,
        title=title,
        entry_ids=sorted(set(entry_ids)),
        evidence=evidence,
        amount_at_risk_inr=_safe_amount(amount),
        likelihood=likelihood,
        impact=impact,
        score=likelihood * impact,
        rationale=rationale,
        status="pending",
    )


def build_ranked_findings() -> dict:
    """Run deterministic checks and return structured, ranked findings."""

    findings: list[Finding] = []

    # 1. Duplicate payments
    duplicate = find_duplicates()
    duplicate_stats = duplicate.get("stats", {})
    duplicate_groups = duplicate_stats.get("groups", [])

    for index, group in enumerate(duplicate_groups, start=1):
        amount = _safe_amount(group.get("amount_inr"))
        entries = group.get("entry_ids", [])

        findings.append(
            _make_finding(
                finding_id=f"R-DUP-{index:03d}",
                category="duplicate_payment",
                title="Potential duplicate vendor payment",
                entry_ids=entries,
                evidence=[
                    f"Vendor: {group.get('vendor_id', 'Unknown')}",
                    f"Payment amount: INR {amount:,.2f}",
                    f"Dates: {', '.join(group.get('dates', []))}",
                ],
                amount=amount,
                likelihood=5,
                impact=5 if amount >= 1_000_000 else (
                    4 if amount >= 100_000 else 3
                ),
                rationale=(
                    "The deterministic duplicate-payment tool identified "
                    "matching vendor payment records. Exposure counts one "
                    "payment amount per duplicate group."
                ),
            )
        )

    # 2. Split payments
    split = find_split_payments()
    split_groups = split.get("stats", {}).get("clusters", [])

    for index, group in enumerate(split_groups, start=1):
        amount = _safe_amount(group.get("total_amount_inr"))

        findings.append(
            _make_finding(
                finding_id=f"R-SPLIT-{index:03d}",
                category="split_payment",
                title="Potential structured payments below approval threshold",
                entry_ids=group.get("entry_ids", []),
                evidence=[
                    f"Vendor: {group.get('vendor_id', 'Unknown')}",
                    f"Number of payments: {group.get('entry_count', 0)}",
                    f"Cluster total: INR {amount:,.2f}",
                ],
                amount=amount,
                likelihood=4,
                impact=5 if amount >= 1_000_000 else (
                    4 if amount >= 100_000 else 3
                ),
                rationale=(
                    "Multiple near-threshold payments were grouped by the "
                    "deterministic split-payment test. Approval evasion "
                    "requires verification against approval records."
                ),
            )
        )

    # 3. Weekend and round-amount postings
    weekend = find_weekend_round()
    weekend_stats = weekend.get("stats", {})
    weekend_ids = weekend.get("flagged_ids", [])
    weekend_amount = _safe_amount(
        weekend_stats.get("total_flagged_amount_inr")
    )

    if weekend_ids:
        findings.append(
            _make_finding(
                finding_id="R-WEEKEND-001",
                category="weekend_posting",
                title="Manual weekend round-amount postings",
                entry_ids=weekend_ids,
                evidence=[
                    f"Flagged ledger entries: {len(weekend_ids)}",
                    (
                        "Flagged transactions: "
                        f"{weekend_stats.get('flagged_transactions_count', 0)}"
                    ),
                    f"Total flagged amount: INR {weekend_amount:,.2f}",
                ],
                amount=weekend_amount,
                likelihood=4,
                impact=4,
                rationale=(
                    "The deterministic weekend test identified Sunday "
                    "round-amount postings. These require verification "
                    "against authorized posting records."
                ),
            )
        )

    # 4. Vendor and employee bank-account overlap
    vendor = vendor_bank_overlap()
    vendor_stats = vendor.get("stats", {})
    vendor_ids = vendor.get("flagged_ids", [])
    vendor_amount = _safe_amount(vendor_stats.get("total_exposure_inr"))

    if vendor_ids:
        shared = vendor_stats.get("shared_details", [])
        findings.append(
            _make_finding(
                finding_id="R-VENDOR-001",
                category="vendor_compliance",
                title="Vendor banking and onboarding control risks",
                entry_ids=vendor_ids,
                evidence=[
                    (
                        "Shared vendor-employee bank accounts: "
                        f"{vendor_stats.get('shared_bank_accounts_count', 0)}"
                    ),
                    (
                        "Missing GSTIN vendors: "
                        f"{vendor_stats.get('missing_gstin_vendors_count', 0)}"
                    ),
                    (
                        "Malformed GSTIN vendors: "
                        f"{vendor_stats.get('malformed_gstin_vendors_count', 0)}"
                    ),
                    (
                        "Cooling-off violations: "
                        f"{vendor_stats.get('cooling_violation_vendors_count', 0)}"
                    ),
                    f"Shared account details inspected: {len(shared)}",
                ],
                amount=vendor_amount,
                likelihood=5,
                impact=5 if vendor_amount >= 1_000_000 else 4,
                rationale=(
                    "The deterministic vendor checks identified shared "
                    "bank-account relationships and onboarding exceptions. "
                    "These are control risks requiring independent verification."
                ),
            )
        )

    # 5. Self-approval and approval-limit violations
    approval = check_approval_limits()
    approval_ids = approval.get("flagged_ids", [])

    if approval_ids:
        approval_stats = approval.get("stats", {})
        approval_amount = _safe_amount(
            approval_stats.get("self_approved_exposure_inr", 0)
        )

        findings.append(
            _make_finding(
                finding_id="R-APPROVAL-001",
                category="approval_control",
                title="Self-approved or over-limit transactions",
                entry_ids=approval_ids,
                evidence=[
                    (
                        "Self-approved transactions: "
                        f"{approval_stats.get('self_approved_transaction_count', 0)} "
                        f"across {approval_stats.get('self_approved_count', 0)} journal lines"
                    ),
                    (
                        "Self-approved exposure: "
                        f"INR {approval_amount:,.2f}"
                    ),
		    (
                        "Over-limit transactions: "
                        f"{approval_stats.get('over_limit_count', 0)}"
                    ),
                ],
                amount=approval_amount,
                likelihood=5,
                impact=4,
                rationale=(
                    "The deterministic approval check identified "
                    "self-approval or approval-limit exceptions."
                ),
            )
        )

    # 6. Benford statistical indicator
    benford = benford_test()
    benford_stats = benford.get("stats", {})
    benford_ids = benford.get("flagged_ids", [])

    if benford_ids:
        findings.append(
            _make_finding(
                finding_id="R-BENFORD-001",
                category="statistical_anomaly",
                title="Unusual first-digit distribution",
                entry_ids=benford_ids,
                evidence=[
                    f"Sample size: {benford_stats.get('sample_size', 0)}",
                    (
                        "Chi-square statistic: "
                        f"{benford_stats.get('chi_square_statistic', 0)}"
                    ),
                    (
                        "Mean absolute deviation: "
                        f"{benford_stats.get('mean_absolute_deviation', 0)}"
                    ),
                    (
                        "Anomalous digits: "
                        f"{benford_stats.get('anomalous_digits', [])}"
                    ),
                ],
                amount=0,
                likelihood=3,
                impact=2,
                rationale=(
                    "The Benford test identified unusual digit frequencies. "
                    "This is a screening indicator, not proof of fraud or "
                    "a directly measurable financial loss."
                ),
            )
        )

    # 7. Monthly financial distress
    # Ratio tool IDs are month identifiers, not journal entry IDs.
    # Do not put them into Finding.entry_ids.
    ratios = ratio_table()
    ratio_stats = ratios.get("stats", {})
    monthly = ratio_stats.get("monthly_ratios", [])
    distressed = [
        row for row in monthly if row.get("is_distressed")
    ]

    # Financial ratio indicators will be included later through a
    # separate evidence structure that does not require journal IDs.

    # Highest risk score first, then exposure, then stable ID.
    findings.sort(
        key=lambda item: (
            -item.score,
            -item.amount_at_risk_inr,
            item.id,
        )
    )

    return {
        "findings": [item.model_dump() for item in findings],
        "total_findings": len(findings),
        "total_amount_at_risk_inr": round(
            sum(item.amount_at_risk_inr for item in findings), 2
        ),
    }
