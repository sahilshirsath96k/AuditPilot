"""Data integrity and general ledger ingestion tools for financial audits."""

from pathlib import Path
from typing import Any
import pandas as pd


def load_ledger(
    ledger_path: str = "data/ledger.csv",
    expected_row_count: int | None = 6000,
    fy_start: str = "2025-04-01",
    fy_end: str = "2026-03-31",
) -> dict[str, Any]:
    """Validate and inspect the general ledger dataset.

    Verifies existence, required schema columns, row count, fiscal date boundaries,
    validity and non-negativity of numeric amounts, and double-entry mathematical balance.

    Args:
        ledger_path: Path to the general ledger CSV file.
        expected_row_count: Expected number of rows in the dataset (default: 6000).
                            Set to None or custom integer for smaller test datasets.
        fy_start: Start date of the fiscal year (default: '2025-04-01').
        fy_end: End date of the fiscal year (default: '2026-03-31').

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('load_ledger').
            - flagged_ids: List of entry_ids that violate accounting constraints.
            - stats: Detailed metrics on rows, columns, dates, numeric validity, and debit/credit totals.
            - notes: Summary assessment of ledger validity and balance.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {
            "test": "load_ledger",
            "flagged_ids": [],
            "stats": {"file_exists": False, "file_path": str(path), "is_valid": False},
            "notes": f"CRITICAL: Ledger file not found at path: {ledger_path}",
        }

    ledger = pd.read_csv(path)
    required_cols = [
        "entry_id",
        "date",
        "posted_by",
        "approved_by",
        "account_code",
        "account_name",
        "vendor_id",
        "debit_inr",
        "credit_inr",
        "amount_inr",
        "description",
    ]
    missing_cols = [c for c in required_cols if c not in ledger.columns]
    if missing_cols:
        return {
            "test": "load_ledger",
            "flagged_ids": [],
            "stats": {
                "file_exists": True,
                "missing_columns": missing_cols,
                "present_columns": list(ledger.columns),
                "is_valid": False,
            },
            "notes": f"CRITICAL: Ledger is missing required columns: {missing_cols}",
        }

    # 1. Validate numeric fields explicitly (never silently coerce or replace invalid values with 0)
    numeric_cols = ["debit_inr", "credit_inr", "amount_inr"]
    invalid_numeric_eids: list[str] = []
    negative_eids: list[str] = []
    col_numeric_errors: dict[str, int] = {}

    for col in numeric_cols:
        coerced = pd.to_numeric(ledger[col], errors="coerce")
        bad_mask = coerced.isna() | ledger[col].isna()
        bad_count = int(bad_mask.sum())
        col_numeric_errors[col] = bad_count
        if bad_count > 0:
            invalid_numeric_eids.extend(ledger.loc[bad_mask, "entry_id"].astype(str).tolist())

        # Check negative amounts among valid numbers
        neg_mask = coerced < 0
        if neg_mask.any():
            negative_eids.extend(ledger.loc[neg_mask, "entry_id"].astype(str).tolist())

    invalid_numeric_eids = sorted(list(set(invalid_numeric_eids)))
    negative_eids = sorted(list(set(negative_eids)))

    # 2. Compute debit/credit sums only if numeric values are fully valid
    if not invalid_numeric_eids:
        debit_sum = round(float(pd.to_numeric(ledger["debit_inr"]).sum()), 2)
        credit_sum = round(float(pd.to_numeric(ledger["credit_inr"]).sum()), 2)
        diff = round(abs(debit_sum - credit_sum), 4)
        is_balanced = diff < 0.01
    else:
        debit_sum = None
        credit_sum = None
        diff = None
        is_balanced = False

    # 3. Date boundary and format validation
    date_series = pd.to_datetime(ledger["date"], errors="coerce")
    invalid_date_eids = ledger[date_series.isna()]["entry_id"].astype(str).tolist()

    fy_start_dt = pd.Timestamp(fy_start)
    fy_end_dt = pd.Timestamp(fy_end)
    out_of_range_mask = (date_series < fy_start_dt) | (date_series > fy_end_dt)
    out_of_range_eids = ledger[out_of_range_mask & date_series.notna()]["entry_id"].astype(str).tolist()

    all_date_violations = sorted(list(set(invalid_date_eids + out_of_range_eids)))

    # 4. Row count validation
    row_count = int(len(ledger))
    row_count_valid = True if expected_row_count is None else (row_count == expected_row_count)

    # 5. Combine constraint violations
    flagged_ids = sorted(list(set(invalid_numeric_eids + negative_eids + all_date_violations)))

    start_date = (
        date_series.min().strftime("%Y-%m-%d")
        if not date_series.empty and date_series.notna().any()
        else None
    )
    end_date = (
        date_series.max().strftime("%Y-%m-%d")
        if not date_series.empty and date_series.notna().any()
        else None
    )

    is_overall_valid = bool(is_balanced and row_count_valid and not flagged_ids)

    stats = {
        "row_count": row_count,
        "expected_row_count": expected_row_count,
        "row_count_valid": row_count_valid,
        "column_count": int(len(ledger.columns)),
        "total_debit_inr": debit_sum,
        "total_credit_inr": credit_sum,
        "balance_difference_inr": diff,
        "is_balanced": is_balanced,
        "numeric_errors": col_numeric_errors,
        "start_date": start_date,
        "end_date": end_date,
        "fiscal_year_range": f"{fy_start} to {fy_end}",
        "date_violations_count": len(all_date_violations),
        "unique_accounts": int(ledger["account_code"].nunique()),
        "unique_entries": int(ledger["entry_id"].nunique()),
        "is_valid": is_overall_valid,
    }

    # 6. Defensive failure reporting in notes
    failure_reasons = []
    if not row_count_valid:
        failure_reasons.append(f"Row count mismatch (expected {expected_row_count}, got {row_count})")
    if invalid_numeric_eids:
        failure_reasons.append(f"{len(invalid_numeric_eids)} entries with non-numeric or missing numeric values")
    if negative_eids:
        failure_reasons.append(f"{len(negative_eids)} entries with negative values")
    if all_date_violations:
        failure_reasons.append(f"{len(all_date_violations)} entries with invalid dates or dates outside FY {fy_start} to {fy_end}")
    if not is_balanced:
        if diff is not None:
            failure_reasons.append(f"Ledger out of balance by Rs {diff:,.2f} (Total Dr: Rs {debit_sum:,.2f}, Total Cr: Rs {credit_sum:,.2f})")
        else:
            failure_reasons.append("Ledger balance could not be calculated due to non-numeric values")

    if not failure_reasons:
        notes = (
            f"Ledger verified successfully. Contains {row_count:,} rows from {start_date} to {end_date} (FY 2025-26). "
            f"Double-entry bookkeeping is balanced (Total Dr: Rs {debit_sum:,.2f}, Total Cr: Rs {credit_sum:,.2f})."
        )
    else:
        notes = "CRITICAL: Ledger validation failed! Issues: " + "; ".join(failure_reasons) + "."

    return {
        "test": "load_ledger",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }
