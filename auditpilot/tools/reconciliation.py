"""Reconciliation tools for general ledger and trial balance verification."""

from pathlib import Path
from typing import Any
import pandas as pd


def check_trial_balance(
    ledger_path: str = "data/ledger.csv",
    tb_path: str = "data/trial_balance.csv",
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Reconcile general ledger account sums against trial balance records.

    Compares aggregate debits and credits for each account between the general
    ledger and trial_balance.csv. Any account where the ledger sum differs
    from the trial balance beyond tolerance is identified, and associated candidate
    journal entries matching the gap amount are flagged for audit scrutiny.

    Args:
        ledger_path: Path to the general ledger CSV file.
        tb_path: Path to the trial balance CSV file.
        tolerance: Allowed floating-point variance for balance parity (default: 0.01).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('check_trial_balance').
            - flagged_ids: List of entry_ids associated with identified account gaps.
            - stats: Detailed reconciliation statistics by account and total discrepancy.
            - notes: Summary of reconciliation findings.
    """
    l_path = Path(ledger_path)
    t_path = Path(tb_path)

    if not l_path.exists() or not t_path.exists():
        return {
            "test": "check_trial_balance",
            "flagged_ids": [],
            "stats": {"ledger_exists": l_path.exists(), "tb_exists": t_path.exists(), "reconciled": False},
            "notes": "CRITICAL: Missing ledger or trial balance file for reconciliation.",
        }

    ledger = pd.read_csv(l_path)
    tb = pd.read_csv(t_path)

    # 1. Validate required columns in both CSV files
    req_gl_cols = ["entry_id", "account_code", "debit_inr", "credit_inr", "amount_inr"]
    missing_gl = [c for c in req_gl_cols if c not in ledger.columns]

    req_tb_cols = ["account_code", "account_name", "total_debit", "total_credit"]
    missing_tb = [c for c in req_tb_cols if c not in tb.columns]

    if missing_gl or missing_tb:
        err_msg = []
        if missing_gl:
            err_msg.append(f"Ledger missing columns: {missing_gl}")
        if missing_tb:
            err_msg.append(f"Trial balance missing columns: {missing_tb}")
        return {
            "test": "check_trial_balance",
            "flagged_ids": [],
            "stats": {
                "ledger_missing_columns": missing_gl,
                "tb_missing_columns": missing_tb,
                "reconciled": False,
            },
            "notes": "CRITICAL: Reconciliation aborted due to missing schema columns. " + "; ".join(err_msg),
        }

    # 2. Check for invalid non-numeric values in trial balance (never silently replace with zero)
    tb_dr_num = pd.to_numeric(tb["total_debit"], errors="coerce")
    tb_cr_num = pd.to_numeric(tb["total_credit"], errors="coerce")
    bad_tb_dr = tb[tb_dr_num.isna()]["account_code"].tolist()
    bad_tb_cr = tb[tb_cr_num.isna()]["account_code"].tolist()

    if bad_tb_dr or bad_tb_cr:
        bad_accs = sorted(list(set(bad_tb_dr + bad_tb_cr)))
        return {
            "test": "check_trial_balance",
            "flagged_ids": [],
            "stats": {
                "invalid_numeric_tb_accounts": bad_accs,
                "reconciled": False,
            },
            "notes": f"CRITICAL: Trial balance contains invalid non-numeric balances on accounts: {bad_accs}.",
        }

    # 3. Check for invalid non-numeric values in ledger (never silently replace with zero)
    gl_dr_num = pd.to_numeric(ledger["debit_inr"], errors="coerce")
    gl_cr_num = pd.to_numeric(ledger["credit_inr"], errors="coerce")
    gl_amt_num = pd.to_numeric(ledger["amount_inr"], errors="coerce")
    bad_gl_mask = gl_dr_num.isna() | gl_cr_num.isna() | gl_amt_num.isna()

    if bad_gl_mask.any():
        bad_gl_eids = ledger.loc[bad_gl_mask, "entry_id"].astype(str).tolist()
        return {
            "test": "check_trial_balance",
            "flagged_ids": bad_gl_eids,
            "stats": {
                "invalid_numeric_gl_entries": bad_gl_eids,
                "reconciled": False,
            },
            "notes": f"CRITICAL: Ledger contains {len(bad_gl_eids)} entries with non-numeric values during reconciliation.",
        }

    # 4. Compute ledger debits and credits by account
    ledger_debits = (
        ledger.assign(_dr=gl_dr_num).groupby("account_code")["_dr"].sum().to_dict()
    )
    ledger_credits = (
        ledger.assign(_cr=gl_cr_num).groupby("account_code")["_cr"].sum().to_dict()
    )

    gaps = []
    flagged_ids: list[str] = []

    for idx, row in tb.iterrows():
        code = row["account_code"]
        name = row["account_name"]
        tb_dr = float(tb_dr_num.iloc[idx])
        tb_cr = float(tb_cr_num.iloc[idx])

        l_dr = float(ledger_debits.get(code, 0.0))
        l_cr = float(ledger_credits.get(code, 0.0))

        dr_diff = round(l_dr - tb_dr, 2)
        cr_diff = round(l_cr - tb_cr, 2)

        if abs(dr_diff) > tolerance or abs(cr_diff) > tolerance:
            gaps.append(
                {
                    "account_code": code,
                    "account_name": name,
                    "ledger_debit": l_dr,
                    "tb_debit": tb_dr,
                    "debit_gap": dr_diff,
                    "ledger_credit": l_cr,
                    "tb_credit": tb_cr,
                    "credit_gap": cr_diff,
                }
            )

            # Search ledger entries for candidate entries matching the discrepancy within tolerance
            gap_amount = abs(dr_diff) if abs(dr_diff) > tolerance else abs(cr_diff)
            candidates = ledger[
                (ledger["account_code"] == code)
                & (abs(gl_amt_num - gap_amount) <= tolerance)
            ]["entry_id"].tolist()

            if candidates:
                flagged_ids.extend(candidates)
            else:
                # If no single entry matches the gap within tolerance, flag all entries on that account
                all_acc_entries = ledger[ledger["account_code"] == code][
                    "entry_id"
                ].tolist()
                flagged_ids.extend(all_acc_entries)

    flagged_ids = sorted(list(set(flagged_ids)))

    stats = {
        "accounts_reconciled": int(len(tb)),
        "discrepant_accounts_count": int(len(gaps)),
        "discrepancies": gaps,
        "total_discrepancy_inr": sum(
            abs(g["debit_gap"]) + abs(g["credit_gap"]) for g in gaps
        ),
        "reconciled": (len(gaps) == 0),
    }

    if not gaps:
        notes = f"All {len(tb)} accounts in trial balance fully reconciled with general ledger (0.00 discrepancy)."
    else:
        acc_summaries = [
            f"Account {g['account_code']} ({g['account_name']}): debit gap Rs {g['debit_gap']:,.2f}, credit gap Rs {g['credit_gap']:,.2f}"
            for g in gaps
        ]
        notes = (
            f"Found {len(gaps)} account discrepancy between ledger and trial balance: "
            + "; ".join(acc_summaries)
        )

    return {
        "test": "check_trial_balance",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }
