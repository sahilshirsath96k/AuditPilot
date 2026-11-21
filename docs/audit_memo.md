---
# AUDIT MEMORANDUM
**Status: DRAFT** (Awaiting Partner Sign-Off)
**Entity:** Not independently verified from source ledger files
**Fiscal Period:** 2025-04-01 to 2026-03-31
---

## 1. Scope and Data

- **Audit Period:** 2025-04-01 to 2026-03-31
- **General Ledger Records:** 6,000 journal entries across 11 columns
- **Double-Entry Bookkeeping:** Balanced (Total Debits: ₹171,175,194.18 | Total Credits: ₹171,175,194.18)
- **Trial Balance Reconciliation:** Unreconciled with Variance
  - **Identified Gap:** ₹125,000.00
  - **Discrepant Accounts:** None identified
  - **Candidate Entry IDs:** JE-2025-2767

## 2. Executive Summary

AuditPilot conducted a comprehensive, multi-agent forensic audit of the general ledger, vendor disbursements, and corporate governance controls for FY 2025–26. All transactions were evaluated against corporate standard operating procedures (SOP-FIN-PROC-2025-V1) and Indian Accounting Standards (Ind AS).

### Summary of Findings:
- **Total Findings Analyzed:** 3
- **Confirmed Findings:** 1
- **Findings Requiring Further Evidence:** 1
- **Dropped Findings (in Appendix):** 1

> [!NOTE] **Note on Financial Exposure:**
> Category-level financial exposures can overlap across accounting dimensions (e.g., an unauthorized payment may also > be flagged under weekend timing or round amounts) and must not be interpreted as unique additive company losses.

## 3. Ranked Findings (Confirmed)

| Finding ID | Category | Title | Cited Entry IDs | Exposure (INR) | Score |
|---|---|---|---|---|---|
| FIND-001 | Compliance | Segregation of Duties Self-Approval | JE-2025-0101, JE-2025-0102 | ₹85,000.00 | 12 (4×3) |

### FIND-001: Segregation of Duties Self-Approval
- **Category:** Compliance
- **Risk Score:** 12 (Likelihood: 4/5, Impact: 3/5)
- **Amount at Risk:** ₹85,000.00
- **Cited Entry IDs:** JE-2025-0101, JE-2025-0102
- **Supporting Evidence:**
  - Maker EMP-16 posted and approved entry
- **Rationale:** Direct breach of SOP Clause 3.1
- **Skeptic Review:** Verified against employee master: maker equals checker.

## 4. Findings Requiring Additional Evidence

The following findings exhibit statistical anomalies or potential policy variances, but require external or supplementary evidence (such as physical gate passes, delivery challans, or email approvals) before a conclusive breach can be established:

| Finding ID | Title | Cited Entry IDs | Required Evidence / Note |
|---|---|---|---|
| FIND-002 | Potential Split Payment Structuring | JE-2025-0201, JE-2025-0202 | Requires purchase orders and requisitions to verify business purpose. |

## 5. Recommended Actions for Management

1. **Segregation of Duties Enforcement:** Implement system-level maker-checker controls to prevent journal vouchers where `posted_by == approved_by`.
2. **Vendor Master & Payroll Cross-Matching:** Introduce automated checks between employee bank accounts and registered vendor bank accounts.
3. **Approval Threshold Monitoring:** Monitor transaction aggregation against the delegated authority limits defined in the applicable approval policy.
4. **Trial Balance Reconciliation:** Investigate the trial-balance variance of ₹125,000.00 for No discrepant accounts identified. Candidate entry IDs: JE-2025-2767. Reconcile the ledger balances with supporting schedules before posting any adjustment.

## 6. Scope Limitations

- The audit procedures were conducted on provided electronic general ledger and financial schedules for FY 2025–26.
- Audit procedures did not include physical inventory stock verification or direct external bank confirmation circulars.
- Statistical indicators (such as first-digit Benford's Law conformity) serve as screening mechanisms and do not constitute definitive legal evidence of fraudulent activity without corroborating transactional documentation.

## 7. Appendix: Dropped Findings and Review Justification

In accordance with auditing standards, findings that did not meet verification criteria (such as nonexistent journal entry IDs or unsupported initial hypotheses) are retained below with full transparency:

| Finding ID | Category | Title | Cited Entry IDs | Reason for Dropping |
|---|---|---|---|---|
| FIND-003 | Vendor | Nonexistent Journal Entry Claim | INVALID-JE-9999 | Journal entry ID verification failed: 1 supplied journal entry ID(s) do not exist. |

## 8. Partner Sign-Off Record

| Field | Status Details |
|---|---|
| **Memorandum Status** | **DRAFT** (Awaiting Partner Sign-Off) |
| **Sign-Off Authority** | Audit Engagement Partner |
| **Review Decision** | Pending Formal Partner Review |
