"""Statistical and pattern-based anomaly detection tools for journal entries."""

from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd


def benford_test(
    ledger_path: str = "data/ledger.csv",
    mad_threshold: float = 0.012,
    residual_threshold: float = 2.5,
) -> dict[str, Any]:
    """Perform first-digit Benford's Law analysis on ledger transaction amounts.

    Extracts the leading significant digit (1-9) from all non-zero transaction amounts
    in the general ledger, compares empirical frequencies against the theoretical
    Benford logarithmic distribution (P(d) = log10(1 + 1/d)), and performs goodness-of-fit
    evaluations using Chi-Square and Mean Absolute Deviation (MAD). Digits with
    standardized residuals exceeding residual_threshold are flagged as anomalies.

    Args:
        ledger_path: Path to the general ledger CSV file.
        mad_threshold: Mean Absolute Deviation threshold for non-conformity (default: 0.012).
        residual_threshold: Z-score residual threshold for flagging an individual digit (default: 2.5).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('benford_test').
            - flagged_ids: List of entry_ids associated with anomalous digit spikes.
            - stats: Observed and expected digit counts, chi-square, MAD, and conformity level.
            - notes: Forensic analysis narrative detailing conformity or specific digit spikes.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {
            "test": "benford_test",
            "flagged_ids": [],
            "stats": {"file_exists": False},
            "notes": f"CRITICAL: Ledger file not found at path: {ledger_path}",
        }

    ledger = pd.read_csv(path)
    required_cols = ["entry_id", "debit_inr", "amount_inr"]
    missing = [c for c in required_cols if c not in ledger.columns]
    if missing:
        return {
            "test": "benford_test",
            "flagged_ids": [],
            "stats": {"missing_columns": missing},
            "notes": f"CRITICAL: Missing required columns for Benford analysis: {missing}",
        }

    debit_num = pd.to_numeric(ledger["debit_inr"], errors="coerce")
    amount_num = pd.to_numeric(ledger["amount_inr"], errors="coerce")

    # Use non-zero debit entries (or primary operational entries where debit_inr > 0)
    # to avoid double-counting both legs of every transaction

    # Use debit values when available; otherwise fall back to transaction amounts.
    values = debit_num if (debit_num > 0).any() else amount_num
    pos_mask = values > 0

    pos_entries = ledger[pos_mask].copy()
    pos_entries["val_num"] = values[pos_mask]

    # Extract first significant digit
    def extract_first_digit(val: float) -> int:
        if pd.isna(val) or val <= 0:
            return 0
        s = f"{val:.2f}".replace(".", "").lstrip("0")
        return int(s[0]) if s else 0

    pos_entries["first_digit"] = pos_entries["val_num"].apply(extract_first_digit)
    valid_entries = pos_entries[pos_entries["first_digit"].between(1, 9)]

    total_n = len(valid_entries)
    if total_n == 0:
        return {
            "test": "benford_test",
            "flagged_ids": [],
            "stats": {"total_transactions": 0},
            "notes": "No valid non-zero transaction amounts available for Benford analysis.",
        }

    counts = valid_entries["first_digit"].value_counts().to_dict()

    digit_stats = {}
    chi_square = 0.0
    mad_sum = 0.0
    anomalous_digits = []

    for d in range(1, 10):
        obs = counts.get(d, 0)
        exp_prob = np.log10(1 + 1 / d)
        exp_count = total_n * exp_prob
        obs_prob = obs / total_n
        diff_prob = obs_prob - exp_prob

        # Standardized residual: (O - E) / sqrt(E)
        std_res = (obs - exp_count) / np.sqrt(exp_count) if exp_count > 0 else 0.0
        chi_contrib = ((obs - exp_count) ** 2) / exp_count if exp_count > 0 else 0.0

        chi_square += chi_contrib
        mad_sum += abs(diff_prob)

        if abs(std_res) >= residual_threshold:
            anomalous_digits.append(d)

        digit_stats[str(d)] = {
            "observed_count": int(obs),
            "expected_count": round(float(exp_count), 2),
            "observed_pct": round(float(obs_prob * 100), 2),
            "expected_pct": round(float(exp_prob * 100), 2),
            "diff_pct": round(float(diff_prob * 100), 2),
            "standardized_residual": round(float(std_res), 2),
            "is_anomaly": bool(abs(std_res) >= residual_threshold),
        }

    mad = round(float(mad_sum / 9.0), 4)
    chi_square = round(float(chi_square), 2)

    # Nigrini MAD conformity evaluation
    if mad <= 0.006:
        conformity = "Close conformity"
    elif mad <= 0.012:
        conformity = "Acceptable conformity"
    elif mad <= 0.015:
        conformity = "Marginally acceptable conformity"
    else:
        conformity = "Non-conformity"

    # Flag entry_ids belonging to anomalous digit spikes
    flagged_entries = valid_entries[
        valid_entries["first_digit"].isin(anomalous_digits)
    ]
    flagged_ids = sorted(flagged_entries["entry_id"].tolist())

    stats = {
        "sample_size": total_n,
        "chi_square_statistic": chi_square,
        "degrees_of_freedom": 8,
        "mean_absolute_deviation": mad,
        "conformity_assessment": conformity,
        "anomalous_digits": anomalous_digits,
        "digits": digit_stats,
    }

    if not anomalous_digits:
        notes = (
            f"Benford's Law analysis (N={total_n:,}): Data exhibits {conformity} "
            f"(MAD: {mad:.4f}, Chi-Square: {chi_square:.2f}). No significant digit anomalies detected."
        )
    else:
        spikes = [
            f"Digit {d} (Obs: {digit_stats[str(d)]['observed_pct']}%, Exp: {digit_stats[str(d)]['expected_pct']}%, Z: {digit_stats[str(d)]['standardized_residual']})"
            for d in anomalous_digits
        ]
        notes = (
            f"Benford's Law analysis (N={total_n:,}): Data exhibits {conformity} "
            f"(MAD: {mad:.4f}, Chi-Square: {chi_square:.2f}). Significant statistical spikes detected: "
            + "; ".join(spikes)
            + f". Flagged {len(flagged_ids)} candidate entries."
        )

    return {
        "test": "benford_test",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }


def find_duplicates(
    ledger_path: str = "data/ledger.csv",
    window_days: int = 5,
) -> dict[str, Any]:
    """Detect duplicate payments issued to the same vendor with identical amounts.

    Scans general ledger vendor disbursements for occurrences where the same
    vendor_id is paid the exact same amount_inr multiple times within a rolling
    window of window_days calendar days.

    Args:
        ledger_path: Path to the general ledger CSV file.
        window_days: Maximum interval in days between matching payments (default: 5).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('find_duplicates').
            - flagged_ids: List of entry_ids involved in duplicate payment events.
            - stats: Detailed metrics on duplicate pairs, affected vendors, and amounts.
            - notes: Summary of duplicate payment findings and exposure.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {
            "test": "find_duplicates",
            "flagged_ids": [],
            "stats": {"file_exists": False},
            "notes": f"CRITICAL: Ledger file not found at path: {ledger_path}",
        }

    ledger = pd.read_csv(path)
    required_cols = ["entry_id", "date", "vendor_id", "debit_inr", "amount_inr", "description"]
    missing = [c for c in required_cols if c not in ledger.columns]
    if missing:
        return {
            "test": "find_duplicates",
            "flagged_ids": [],
            "stats": {"missing_columns": missing},
            "notes": f"CRITICAL: Missing required columns for duplicate check: {missing}",
        }

    debit_num = pd.to_numeric(ledger["debit_inr"], errors="coerce")
    amt_num = pd.to_numeric(ledger["amount_inr"], errors="coerce")
    date_dt = pd.to_datetime(ledger["date"], errors="coerce")

    # Filter for valid vendor disbursements (debit entries with non-empty vendor_id)
    v_mask = (
        ledger["vendor_id"].notna()
        & (ledger["vendor_id"].astype(str).str.strip() != "")
        & (debit_num > 0)
        & date_dt.notna()
    )
    v_df = ledger[v_mask].copy()
    v_df["date_dt"] = date_dt[v_mask]
    v_df["amount_num"] = amt_num[v_mask]

    if v_df.empty:
        return {
            "test": "find_duplicates",
            "flagged_ids": [],
            "stats": {"vendor_entries_checked": 0, "duplicate_groups_count": 0},
            "notes": "No vendor debit disbursements found in ledger.",
        }

    v_df = v_df.sort_values(["vendor_id", "date_dt"])

    flagged_ids: list[str] = []
    duplicate_groups = []

    for (vid, amt), grp in v_df.groupby(["vendor_id", "amount_num"]):
        if len(grp) > 1:
            grp = grp.sort_values("date_dt")
            matched_indices = set()
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    diff_days = (
                        grp.iloc[j]["date_dt"] - grp.iloc[i]["date_dt"]
                    ).days
                    if diff_days <= window_days:
                        matched_indices.add(i)
                        matched_indices.add(j)

            if matched_indices:
                matched_rows = grp.iloc[sorted(list(matched_indices))]
                eids = matched_rows["entry_id"].tolist()
                flagged_ids.extend(eids)
                duplicate_groups.append(
                    {
                        "vendor_id": vid,
                        "amount_inr": float(amt),
                        "entry_ids": eids,
                        "dates": matched_rows["date"].tolist(),
                        "descriptions": matched_rows["description"].tolist(),
                    }
                )

    flagged_ids = sorted(list(set(flagged_ids)))
    total_exposure = sum(g["amount_inr"] for g in duplicate_groups)

    stats = {
        "vendor_entries_checked": int(len(v_df)),
        "duplicate_groups_count": int(len(duplicate_groups)),
        "flagged_entries_count": int(len(flagged_ids)),
        "total_exposure_inr": round(float(total_exposure), 2),
        "groups": duplicate_groups,
    }

    if not flagged_ids:
        notes = f"No duplicate vendor disbursements identified within {window_days}-day window across {len(v_df):,} entries."
    else:
        notes = (
            f"Identified {len(duplicate_groups)} duplicate payment clusters ({len(flagged_ids)} total entries) "
            f"with identical vendor and amount within {window_days} days. Total duplicate exposure: Rs {total_exposure:,.2f}."
        )

    return {
        "test": "find_duplicates",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }


def find_split_payments(
    ledger_path: str = "data/ledger.csv",
    lower_limit: float = 45000.0,
    upper_limit: float = 50000.0,
    window_hours: int = 48,
    min_count: int = 2,
) -> dict[str, Any]:
    """Detect structured / split payments designed to circumvent approval limits.

    Scans vendor disbursements for clusters of transactions issued to the same
    vendor within a rolling window_hours window where each transaction amount is
    just below the delegated approval threshold (between lower_limit and upper_limit).
    Uses disjoint temporal clustering to prevent assigning an entry to multiple clusters
    and to prevent double-counting exposure.

    Args:
        ledger_path: Path to the general ledger CSV file.
        lower_limit: Lower bound of near-threshold transaction amounts (default: 45,000 INR).
        upper_limit: Upper approval threshold limit (default: 50,000 INR).
        window_hours: Maximum hours between split transactions (default: 48 hours).
        min_count: Minimum number of near-threshold transactions to form a group (default: 2).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('find_split_payments').
            - flagged_ids: List of entry_ids identified as structured split payments.
            - stats: Detailed breakdown of split payment clusters by vendor.
            - notes: Forensic analysis of structuring activities.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {
            "test": "find_split_payments",
            "flagged_ids": [],
            "stats": {"file_exists": False},
            "notes": f"CRITICAL: Ledger file not found at path: {ledger_path}",
        }

    ledger = pd.read_csv(path)
    required_cols = ["entry_id", "vendor_id", "date", "debit_inr", "amount_inr"]
    missing = [c for c in required_cols if c not in ledger.columns]
    if missing:
        return {
            "test": "find_split_payments",
            "flagged_ids": [],
            "stats": {"missing_columns": missing},
            "notes": f"CRITICAL: Missing required columns for split payment detection: {missing}",
        }

    debit_num = pd.to_numeric(ledger["debit_inr"], errors="coerce")
    amt_num = pd.to_numeric(ledger["amount_inr"], errors="coerce")
    date_dt = pd.to_datetime(ledger["date"], errors="coerce")

    # Filter vendor debit entries
    v_mask = (
        ledger["vendor_id"].notna()
        & (ledger["vendor_id"].astype(str).str.strip() != "")
        & (debit_num > 0)
        & date_dt.notna()
    )
    v_df = ledger[v_mask].copy()
    v_df["date_dt"] = date_dt[v_mask]
    v_df["amount_num"] = amt_num[v_mask]

    if v_df.empty:
        return {
            "test": "find_split_payments",
            "flagged_ids": [],
            "stats": {"candidate_count": 0, "split_groups_count": 0},
            "notes": "No vendor debit disbursements found in ledger.",
        }

    # Near-threshold candidate entries
    candidates = v_df[
        (v_df["amount_num"] >= lower_limit) & (v_df["amount_num"] < upper_limit)
    ].sort_values(["vendor_id", "date_dt"])

    flagged_ids: list[str] = []
    split_clusters = []

    # Disjoint temporal clustering per vendor: prevents multiple cluster assignments and double-counted exposure
    for vid, grp in candidates.groupby("vendor_id"):
        grp = grp.sort_values("date_dt")
        current_cluster: list[dict[str, Any]] = []

        for _, row in grp.iterrows():
            if not current_cluster:
                current_cluster.append(row.to_dict())
            else:
                diff_hours = (row["date_dt"] - current_cluster[-1]["date_dt"]).total_seconds() / 3600.0
                if diff_hours <= window_hours:
                    current_cluster.append(row.to_dict())
                else:
                    if len(current_cluster) >= min_count:
                        c_eids = [r["entry_id"] for r in current_cluster]
                        c_amts = [float(r["amount_num"]) for r in current_cluster]
                        c_dates = [r["date_dt"].strftime("%Y-%m-%d") for r in current_cluster]
                        flagged_ids.extend(c_eids)
                        split_clusters.append({
                            "vendor_id": vid,
                            "entry_count": len(c_eids),
                            "total_amount_inr": round(float(sum(c_amts)), 2),
                            "entry_ids": c_eids,
                            "amounts": c_amts,
                            "dates": c_dates,
                        })
                    current_cluster = [row.to_dict()]

        if len(current_cluster) >= min_count:
            c_eids = [r["entry_id"] for r in current_cluster]
            c_amts = [float(r["amount_num"]) for r in current_cluster]
            c_dates = [r["date_dt"].strftime("%Y-%m-%d") for r in current_cluster]
            flagged_ids.extend(c_eids)
            split_clusters.append({
                "vendor_id": vid,
                "entry_count": len(c_eids),
                "total_amount_inr": round(float(sum(c_amts)), 2),
                "entry_ids": c_eids,
                "amounts": c_amts,
                "dates": c_dates,
            })

    flagged_ids = sorted(list(set(flagged_ids)))
    total_split_value = sum(c["total_amount_inr"] for c in split_clusters)

    stats = {
        "near_threshold_entries_checked": int(len(candidates)),
        "split_groups_count": int(len(split_clusters)),
        "flagged_entries_count": int(len(flagged_ids)),
        "total_structured_amount_inr": round(float(total_split_value), 2),
        "clusters": split_clusters,
    }

    if not flagged_ids:
        notes = f"No structured split payments identified between Rs {lower_limit:,.2f} and Rs {upper_limit:,.2f} within {window_hours} hours."
    else:
        notes = (
            f"Detected {len(split_clusters)} structured split-payment groups ({len(flagged_ids)} total entries) "
            f"to {len(split_clusters)} vendors within {window_hours} hours near the Rs {upper_limit:,.2f} threshold. "
            f"Total structured amount: Rs {total_split_value:,.2f}."
        )

    return {
        "test": "find_split_payments",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }


def find_weekend_round(
    ledger_path: str = "data/ledger.csv",
    round_base: float = 10000.0,
    sundays_only: bool = True,
) -> dict[str, Any]:
    """Identify off-hour transactions posted on Sundays with exact round INR amounts.

    Enforces Corporate Policy Clause 5.2 & 5.3 prohibiting weekend manual journal entries
    and flagging round-amount disbursements (exact multiples of round_base) posted on non-working days.
    Explicitly distinguishes between ledger rows (entry IDs) and economic transactions.

    Args:
        ledger_path: Path to the general ledger CSV file.
        round_base: Multiple used to define a round amount (default: 10,000 INR).
        sundays_only: If True, restricts check to Sundays (day_of_week == 6).
                      If False, checks entire weekend (Saturday & Sunday).

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('find_weekend_round').
            - flagged_ids: List of entry_ids matching weekend round amount criteria.
            - stats: Detailed counts, date breakdown, and total flagged volume.
            - notes: Summary of weekend round-amount findings.
    """
    path = Path(ledger_path)
    if not path.exists():
        return {
            "test": "find_weekend_round",
            "flagged_ids": [],
            "stats": {"file_exists": False},
            "notes": f"CRITICAL: Ledger file not found at path: {ledger_path}",
        }

    ledger = pd.read_csv(path)
    required_cols = ["entry_id", "date", "amount_inr"]
    missing = [c for c in required_cols if c not in ledger.columns]
    if missing:
        return {
            "test": "find_weekend_round",
            "flagged_ids": [],
            "stats": {"missing_columns": missing},
            "notes": f"CRITICAL: Missing required columns for weekend round test: {missing}",
        }

    date_dt = pd.to_datetime(ledger["date"], errors="coerce")
    amt_num = pd.to_numeric(ledger["amount_inr"], errors="coerce")

    if sundays_only:
        day_mask = date_dt.dt.day_of_week == 6
        target_name = "Sunday"
    else:
        day_mask = date_dt.dt.day_of_week >= 5
        target_name = "Weekend"

    round_mask = (amt_num % round_base == 0) & (amt_num > 0)
    flagged_df = ledger[day_mask & round_mask].copy()

    flagged_ids = sorted(flagged_df["entry_id"].tolist())
    total_val = round(float(amt_num[day_mask & round_mask].sum()), 2)

    by_date = (
        flagged_df.groupby("date")
        .agg(entry_count=("entry_id", "count"), total_inr=("amount_inr", "sum"))
        .reset_index()
        .to_dict("records")
    )

    # In balanced double-entry accounting, each transaction generates 2 rows (1 Debit + 1 Credit)
    flagged_entries_count = int(len(flagged_ids))
    flagged_transactions_count = flagged_entries_count // 2

    stats = {
        "total_ledger_rows": int(len(ledger)),
        "weekend_entries_checked": int(day_mask.sum()),
        "flagged_entries_count": flagged_entries_count,
        "flagged_transactions_count": flagged_transactions_count,
        "total_flagged_amount_inr": total_val,
        "round_base_inr": round_base,
        "by_date": by_date,
    }

    if not flagged_ids:
        notes = f"No {target_name.lower()} round-amount entries (multiples of Rs {round_base:,.2f}) detected in ledger."
    else:
        notes = (
            f"Flagged {flagged_entries_count} {target_name.lower()} ledger entries "
            f"(representing {flagged_transactions_count} balanced transactions) posted with exact round amounts "
            f"(multiples of Rs {round_base:,.2f}) totaling Rs {total_val:,.2f}. Breaches SOP Clause 5.2/5.3."
        )

    return {
        "test": "find_weekend_round",
        "flagged_ids": flagged_ids,
        "stats": stats,
        "notes": notes,
    }
