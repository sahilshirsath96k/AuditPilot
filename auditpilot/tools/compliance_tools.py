"""Compliance and governance audit tools: segregation of duties, approval limits, shared banking, and ghost vendors."""

from pathlib import Path
import re
from typing import Any
import pandas as pd


def check_approval_limits(
    ledger_path: str = "data/ledger.csv",
    employees_path: str = "data/employees.csv",
) -> dict[str, Any]:
    """Enforce financial authority matrices and segregation of duties.

    Evaluates journal entries against Corporate Policy SOP Clause 2.1-2.4 and Clause 3.1:
    1. Identifies Segregation of Duties (SoD) breaches: entries where maker and checker
       are identical (posted_by == approved_by).
    2. Identifies Delegated Financial Authority breaches: entries where transaction amount
       exceeds the authorized approval_limit_inr assigned to approved_by in employees.csv.

    Args:
        ledger_path: Path to the general ledger CSV file.
        employees_path: Path to the employees master CSV file.

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('check_approval_limits').
            - flagged_ids: List of entry_ids violating self-approval or limit thresholds.
            - stats: Detailed metrics on self-approved entries and over-limit entries.
            - notes: Summary of compliance and governance exceptions found.
    """
    l_path = Path(ledger_path)
    e_path = Path(employees_path)

    if not l_path.exists() or not e_path.exists():
        return {
            "test": "check_approval_limits",
            "flagged_ids": [],
            "stats": {"ledger_exists": l_path.exists(), "employees_exists": e_path.exists()},
            "notes": "Missing ledger or employees master file.",
        }

    ledger = pd.read_csv(l_path)
    employees = pd.read_csv(e_path)

    emp_limits = dict(zip(employees["employee_id"], employees["approval_limit_inr"]))

    # 1. Self-approval check (SoD violation)
    self_app_mask = ledger["posted_by"] == ledger["approved_by"]
    self_app_entries = ledger[self_app_mask]["entry_id"].tolist()

    # 2. Exceeding approval limit check
    ledger["approver_limit"] = ledger["approved_by"].map(emp_limits).fillna(0.0)
    over_limit_mask = ledger["amount_inr"] > ledger["approver_limit"]
    over_limit_entries = ledger[over_limit_mask]["entry_id"].tolist()

    flagged_ids = sorted(list(set(self_app_entries + over_limit_entries)))

    self_app_summary = (
        ledger[self_app_mask]
        .groupby(["posted_by", "approved_by"])
        .agg(count=("entry_id", "count"), total_inr=("amount_inr", "sum"))
        .reset_index()
        .to_dict("records")
    )

    over_limit_summary = (
        ledger[over_limit_mask]
        .groupby(["approved_by", "approver_limit"])
        .agg(count=("entry_id", "count"), total_inr=("amount_inr", "sum"))
        .reset_index()
        .to_dict("records")
    )

    stats = {
        "total_entries_checked": int(len(ledger)),
        "self_approved_count": int(len(self_app_entries)),
        "over_limit_count": int(len(over_limit_entries)),
        "unique_flagged_count": int(len(flagged_ids)),
        "self_approved_summary": self_app_summary,
        "over_limit_summary": over_limit_summary,
    }

    notes_parts = []
    if self_app_entries:
        notes_parts.append(
            f"Flagged {len(self_app_entries)} self-approved transactions (posted_by == approved_by) breaching SOP Clause 3.1"
        )
    if over_limit_entries:
        notes_parts.append(
            f"Flagged {len(over_limit_entries)} transactions exceeding approver delegated authority limit breaching SOP Clause 2.1-2.3"
        )
    if not flagged_ids:
        notes = "All ledger transactions comply with segregation of duties and authority limits."
    else:
        notes = ". ".join(notes_parts) + "."

    return {
        "test": "check_approval_limits",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }


def vendor_bank_overlap(
    ledger_path: str = "data/ledger.csv",
    vendors_path: str = "data/vendors.csv",
    employees_path: str = "data/employees.csv",
    min_cooling_days: int = 5,
) -> dict[str, Any]:
    """Identify conflicts of interest, shared banking credentials, and ghost vendors.

    Cross-checks vendor master records against employee payroll bank accounts and statutory
    verification rules in accordance with Corporate Policy SOP Clause 3.2 and Clause 5.1:
    1. Shared Bank Accounts: Identifies commercial vendors whose bank account numbers match
       active employees and retrieves all associated payment disbursements.
    2. Ghost Vendors: Detects vendors with missing GSTIN, malformed GSTIN formats (non-15
       characters or invalid syntax), or onboarding cooling-off period violations (< min_cooling_days
       between vendor creation and first payout).

    Args:
        ledger_path: Path to the general ledger CSV file.
        vendors_path: Path to the vendors master CSV file.
        employees_path: Path to the employees master CSV file.
        min_cooling_days: Minimum calendar days required between vendor creation and payout (default: 5).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('vendor_bank_overlap').
            - flagged_ids: List of entry_ids associated with shared banking or ghost vendors.
            - stats: Detailed breakdown of shared accounts, ghost vendors, and exposure.
            - notes: Forensic narrative describing detected vendor risks.
    """
    l_path = Path(ledger_path)
    v_path = Path(vendors_path)
    e_path = Path(employees_path)

    if not l_path.exists() or not v_path.exists() or not e_path.exists():
        return {
            "test": "vendor_bank_overlap",
            "flagged_ids": [],
            "stats": {"files_present": False},
            "notes": "Missing required input files (ledger, vendors, or employees).",
        }

    ledger = pd.read_csv(l_path)
    vendors = pd.read_csv(v_path)
    employees = pd.read_csv(e_path)

    # 1. Shared Bank Account Detection
    # Normalize bank account as string to prevent formatting mismatch
    vendors["bank_account_str"] = vendors["bank_account"].astype(str).str.strip()
    employees["bank_account_str"] = (
        employees["bank_account"].astype(str).str.strip()
    )

    shared_accounts = set(vendors["bank_account_str"]).intersection(
        set(employees["bank_account_str"])
    )
    shared_v_df = vendors[vendors["bank_account_str"].isin(shared_accounts)]
    shared_vids = set(shared_v_df["vendor_id"])

    # Map shared details for stats
    emp_by_acc = employees.set_index("bank_account_str").to_dict("index")
    shared_details = []
    for _, v_row in shared_v_df.iterrows():
        b_acc = v_row["bank_account_str"]
        e_info = emp_by_acc.get(b_acc, {})
        shared_details.append(
            {
                "vendor_id": v_row["vendor_id"],
                "vendor_name": v_row["vendor_name"],
                "employee_id": e_info.get("employee_id"),
                "employee_name": e_info.get("employee_name"),
                "department": e_info.get("department"),
                "bank_account": b_acc,
            }
        )

    # 2. Ghost Vendor Detection
    # 2a. Missing GSTIN
    missing_gstin_vids = set(
        vendors[vendors["gstin"].isna() | (vendors["gstin"].astype(str).str.strip() == "")][
            "vendor_id"
        ]
    )

    # 2b. Malformed GSTIN (Standard Indian GSTIN is 15 alphanumeric characters: 2 state + 10 PAN + 1 entity + 'Z' + 1 checksum)
    gstin_regex = re.compile(
        r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    )
    malformed_gstin_vids = set()
    for _, v_row in vendors.iterrows():
        vid = v_row["vendor_id"]
        if vid in missing_gstin_vids:
            continue
        gst = str(v_row.get("gstin", "")).strip()
        if not gstin_regex.match(gst):
            malformed_gstin_vids.add(vid)

    # 2c. Cooling-off Period Violations (< min_cooling_days between created_date and payout)
    v_created_map = dict(
        zip(vendors["vendor_id"], pd.to_datetime(vendors["created_date"]))
    )
    ledger_v = ledger[
        ledger["vendor_id"].notna()
        & (ledger["vendor_id"] != "")
        & (ledger["debit_inr"] > 0)
    ].copy()
    ledger_v["date_dt"] = pd.to_datetime(ledger_v["date"])
    ledger_v["created_date_dt"] = ledger_v["vendor_id"].map(v_created_map)
    ledger_v["cooling_days"] = (
        ledger_v["date_dt"] - ledger_v["created_date_dt"]
    ).dt.days

    cooling_violations = ledger_v[
        ledger_v["cooling_days"] < min_cooling_days
    ].copy()
    cooling_entry_ids = set(cooling_violations["entry_id"])
    cooling_vids = set(cooling_violations["vendor_id"])

    ghost_vids = missing_gstin_vids.union(malformed_gstin_vids).union(
        cooling_vids
    )

    # Identify matching transactions in ledger
    # For shared vendors: find all ledger entries
    shared_entry_ids = set(
        ledger[ledger["vendor_id"].isin(shared_vids)]["entry_id"]
    )

    # For missing/malformed GSTIN: find ledger entries
    invalid_gst_entry_ids = set(
        ledger[
            ledger["vendor_id"].isin(
                missing_gstin_vids.union(malformed_gstin_vids)
            )
        ]["entry_id"]
    )

    ghost_entry_ids = invalid_gst_entry_ids.union(cooling_entry_ids)
    all_flagged = sorted(list(shared_entry_ids.union(ghost_entry_ids)))

    # Compute exposure
    flagged_df = ledger[ledger["entry_id"].isin(all_flagged)]
    total_exposure = round(float(flagged_df["amount_inr"].sum()), 2)

    stats = {
        "shared_bank_accounts_count": int(len(shared_accounts)),
        "shared_vendors_count": int(len(shared_vids)),
        "shared_bank_entries_count": int(len(shared_entry_ids)),
        "shared_details": shared_details,
        "missing_gstin_vendors_count": int(len(missing_gstin_vids)),
        "malformed_gstin_vendors_count": int(len(malformed_gstin_vids)),
        "cooling_violation_vendors_count": int(len(cooling_vids)),
        "total_ghost_vendors_count": int(len(ghost_vids)),
        "ghost_vendor_entries_count": int(len(ghost_entry_ids)),
        "total_flagged_entries_count": int(len(all_flagged)),
        "total_exposure_inr": total_exposure,
    }

    notes_parts = []
    if shared_vids:
        notes_parts.append(
            f"Detected {len(shared_vids)} vendors sharing bank accounts with internal employees "
            f"({len(shared_entry_ids)} disbursements) violating SOP Clause 3.2"
        )
    if ghost_vids:
        notes_parts.append(
            f"Detected {len(ghost_vids)} ghost/non-compliant vendors ({len(ghost_entry_ids)} disbursements) "
            f"violating GSTIN verification or 5-day cooling-off rules under SOP Clause 5.1"
        )
    if not all_flagged:
        notes = "No shared bank accounts or ghost vendor onboarding violations identified."
    else:
        notes = (
            ". ".join(notes_parts)
            + f". Total disbursement exposure: Rs {total_exposure:,.2f}."
        )

    return {
        "test": "vendor_bank_overlap",
        "flagged_ids": all_flagged,
        "stats": stats,
        "notes": notes,
    }
