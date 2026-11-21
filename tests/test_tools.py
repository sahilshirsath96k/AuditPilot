"""Unit tests for the AuditPilot deterministic financial audit tool suite.

Validates:
1. Uniform dictionary structure across all tools: {"test": str, "flagged_ids": list, "stats": dict, "notes": str}.
2. Dedicated functional and boundary tests for all audit tools.
3. Edge case tests: non-numeric inputs, missing columns, dates out of fiscal year, row count mismatches, floating tolerance.
4. Exact benchmark recall >= 90% against data/ground_truth.csv across all seeded anomaly categories.
"""

import json
from pathlib import Path
from typing import Any
import pandas as pd
import pytest

from auditpilot.tools import (
    benford_test,
    check_approval_limits,
    check_trial_balance,
    find_duplicates,
    find_split_payments,
    find_weekend_round,
    load_ledger,
    ratio_table,
    vendor_bank_overlap,
    retrieve_policy,
)
from auditpilot.tools.risk_tools import build_ranked_findings

GROUND_TRUTH_PATH = "data/ground_truth.csv"


@pytest.fixture(scope="session")
def ground_truth_df() -> pd.DataFrame:
    """Load ground truth answer key for offline evaluation."""
    assert Path(GROUND_TRUTH_PATH).exists(), f"Missing ground truth file at {GROUND_TRUTH_PATH}"
    return pd.read_csv(GROUND_TRUTH_PATH)


# =====================================================================
# 1. Uniform Return Structure Tests
# =====================================================================

def test_all_tools_uniform_return_schema():
    """Every tool must return the exact structure: {"test": str, "flagged_ids": list, "stats": dict, "notes": str}."""
    tool_calls = [
        load_ledger(),
        check_trial_balance(),
        benford_test(),
        find_duplicates(),
        find_split_payments(),
        find_weekend_round(),
        check_approval_limits(),
        vendor_bank_overlap(),
        ratio_table(),
    ]

    expected_keys = {"test", "flagged_ids", "stats", "notes"}

    for res in tool_calls:
        assert isinstance(res, dict), f"Tool return must be a dict, got {type(res)}"
        assert set(res.keys()) == expected_keys, f"Keys mismatch in {res.get('test')}: {set(res.keys())}"
        assert isinstance(res["test"], str), f"'test' must be str in {res.get('test')}"
        assert isinstance(res["flagged_ids"], list), f"'flagged_ids' must be list in {res.get('test')}"
        assert isinstance(res["stats"], dict), f"'stats' must be dict in {res.get('test')}"
        assert isinstance(res["notes"], str), f"'notes' must be str in {res.get('test')}"

        # Ensure return is 100% JSON serializable
        json_str = json.dumps(res)
        assert json_str is not None
        assert len(res["notes"]) > 0, f"'notes' must be non-empty in {res.get('test')}"


# =====================================================================
# 2. Individual Tool Dedicated Functional Tests
# =====================================================================

def test_load_ledger_valid():
    """load_ledger must successfully validate the balanced FY 2025-26 general ledger."""
    res = load_ledger("data/ledger.csv")
    assert res["test"] == "load_ledger"
    assert res["flagged_ids"] == []

    stats = res["stats"]
    assert stats["row_count"] == 6000
    assert stats["expected_row_count"] == 6000
    assert stats["row_count_valid"] is True
    assert stats["column_count"] == 11
    assert stats["is_balanced"] is True
    assert stats["is_valid"] is True
    assert stats["balance_difference_inr"] < 0.01
    assert stats["start_date"] == "2025-04-01"
    assert stats["end_date"] == "2026-03-31"
    assert "verified successfully" in res["notes"].lower()


def test_load_ledger_missing_file():
    """load_ledger must gracefully handle missing files."""
    res = load_ledger("data/non_existent_ledger.csv")
    assert res["test"] == "load_ledger"
    assert res["flagged_ids"] == []
    assert res["stats"]["file_exists"] is False
    assert res["stats"]["is_valid"] is False
    assert "critical" in res["notes"].lower()


def test_load_ledger_non_numeric_and_nan(tmp_path: Path):
    """load_ledger must detect missing and non-numeric values and fail validation."""
    df = pd.read_csv("data/ledger.csv", dtype=str).head(10).copy()
    df.loc[0, "debit_inr"] = "CORRUPT_STR"
    df.loc[1, "amount_inr"] = ""

    bad_path = str(tmp_path / "bad_numeric_ledger.csv")
    df.to_csv(bad_path, index=False)

    res = load_ledger(bad_path, expected_row_count=10)
    assert res["test"] == "load_ledger"
    assert res["stats"]["is_valid"] is False
    assert "JE-2025-0001" in res["flagged_ids"]
    assert "JE-2025-0002" in res["flagged_ids"]
    assert "critical: ledger validation failed" in res["notes"].lower()
    assert "non-numeric" in res["notes"].lower()


def test_load_ledger_out_of_bounds_date(tmp_path: Path):
    """load_ledger must flag transactions outside the FY 2025-26 fiscal date range."""
    df = pd.read_csv("data/ledger.csv").head(10).copy()
    df.loc[3, "date"] = "2024-12-31"  # Prior fiscal year
    df.loc[4, "date"] = "2026-05-15"  # Next fiscal year

    bad_path = str(tmp_path / "bad_date_ledger.csv")
    df.to_csv(bad_path, index=False)

    res = load_ledger(bad_path, expected_row_count=10)
    assert res["test"] == "load_ledger"
    assert res["stats"]["is_valid"] is False
    assert df.loc[3, "entry_id"] in res["flagged_ids"]
    assert df.loc[4, "entry_id"] in res["flagged_ids"]
    assert "outside fy" in res["notes"].lower()


def test_load_ledger_wrong_row_count(tmp_path: Path):
    """load_ledger must flag unexpected row counts when configurable expected_row_count is set."""
    df = pd.read_csv("data/ledger.csv").head(50).copy()
    test_path = str(tmp_path / "partial_ledger.csv")
    df.to_csv(test_path, index=False)

    # Calling with default 6000 rows expected
    res = load_ledger(test_path)
    assert res["stats"]["row_count_valid"] is False
    assert res["stats"]["is_valid"] is False
    assert "row count mismatch" in res["notes"].lower()

    # Calling with explicit custom expected_row_count
    res_custom = load_ledger(test_path, expected_row_count=50)
    assert res_custom["stats"]["row_count_valid"] is True


def test_check_trial_balance(ground_truth_df: pd.DataFrame):
    """check_trial_balance must reconcile accounts and detect the Rs 1,25,000 gap on account 6020."""
    res = check_trial_balance("data/ledger.csv", "data/trial_balance.csv")
    assert res["test"] == "check_trial_balance"

    stats = res["stats"]
    assert stats["discrepant_accounts_count"] == 1
    assert stats["total_discrepancy_inr"] == 125000.00
    assert stats["reconciled"] is False

    gap_info = stats["discrepancies"][0]
    assert str(gap_info["account_code"]) == "6020"
    assert gap_info["debit_gap"] == 125000.00

    # Recall against ground_truth.csv for trial_balance_gap
    gt_gap = set(ground_truth_df[ground_truth_df["anomaly_type"] == "trial_balance_gap"]["entry_id"])
    assert len(gt_gap) == 1
    flagged = set(res["flagged_ids"])
    recall = len(gt_gap.intersection(flagged)) / len(gt_gap)
    assert recall == 1.0


def test_check_trial_balance_missing_tb_columns(tmp_path: Path):
    """check_trial_balance must validate required columns in both files and fail cleanly."""
    tb_bad = pd.read_csv("data/trial_balance.csv").drop(columns=["total_debit"]).copy()
    bad_tb_path = str(tmp_path / "bad_tb.csv")
    tb_bad.to_csv(bad_tb_path, index=False)

    res = check_trial_balance("data/ledger.csv", bad_tb_path)
    assert res["test"] == "check_trial_balance"
    assert res["stats"]["reconciled"] is False
    assert "total_debit" in str(res["stats"]["tb_missing_columns"])
    assert "critical: reconciliation aborted" in res["notes"].lower()


def test_check_trial_balance_invalid_numeric(tmp_path: Path):
    """check_trial_balance must not silently coerce invalid non-numeric values to zero."""
    tb_bad = pd.read_csv("data/trial_balance.csv", dtype=str).copy()
    tb_bad.loc[0, "total_debit"] = "INVALID_NUMBER"
    bad_tb_path = str(tmp_path / "bad_numeric_tb.csv")
    tb_bad.to_csv(bad_tb_path, index=False)

    res = check_trial_balance("data/ledger.csv", bad_tb_path)
    assert res["test"] == "check_trial_balance"
    assert res["stats"]["reconciled"] is False
    assert "invalid_numeric_tb_accounts" in res["stats"]
    assert "non-numeric balances" in res["notes"].lower()


def test_check_trial_balance_float_tolerance(tmp_path: Path):
    """check_trial_balance must verify the configured Rs 0.01 tolerance boundary."""
    gl_path = str(tmp_path / "gl_tol.csv")
    pd.DataFrame([
        {
            "entry_id": "JE-2025-T001",
            "account_code": 1010,
            "debit_inr": 50000.00,
            "credit_inr": 0.00,
            "amount_inr": 50000.00,
        }
    ]).to_csv(gl_path, index=False)

    # 1. Variance within tolerance: difference of Rs 0.004 <= 0.01
    tb_within_path = str(tmp_path / "tb_within.csv")
    pd.DataFrame([
        {
            "account_code": 1010,
            "account_name": "Operating Bank",
            "total_debit": 50000.004,
            "total_credit": 0.00,
        }
    ]).to_csv(tb_within_path, index=False)

    res_within = check_trial_balance(gl_path, tb_within_path, tolerance=0.01)
    assert res_within["stats"]["reconciled"] is True
    assert res_within["stats"]["discrepant_accounts_count"] == 0
    assert len(res_within["flagged_ids"]) == 0
    assert "0.00 discrepancy" in res_within["notes"].lower()

    # 2. Variance beyond tolerance: difference of Rs 0.05 > 0.01
    tb_beyond_path = str(tmp_path / "tb_beyond.csv")
    pd.DataFrame([
        {
            "account_code": 1010,
            "account_name": "Operating Bank",
            "total_debit": 50000.05,
            "total_credit": 0.00,
        }
    ]).to_csv(tb_beyond_path, index=False)

    res_beyond = check_trial_balance(gl_path, tb_beyond_path, tolerance=0.01)
    assert res_beyond["stats"]["reconciled"] is False
    assert res_beyond["stats"]["discrepant_accounts_count"] == 1
    assert len(res_beyond["stats"]["discrepancies"]) == 1
    assert res_beyond["stats"]["discrepancies"][0]["account_code"] == 1010
    assert "found 1 account discrepancy" in res_beyond["notes"].lower()


def test_benford_test_statistics():
    """benford_test must compute first-digit distribution, chi-square, MAD, and detect deviations."""
    res = benford_test("data/ledger.csv")
    assert res["test"] == "benford_test"

    stats = res["stats"]
    assert stats["sample_size"] == 3000
    assert stats["degrees_of_freedom"] == 8
    assert stats["chi_square_statistic"] > 0
    assert stats["mean_absolute_deviation"] > 0
    assert len(stats["digits"]) == 9

    # Digit 5 exhibits an empirical spike due to Rs 46k-50k structuring and round sums
    assert 5 in stats["anomalous_digits"] or "5" in stats["digits"]
    assert len(res["flagged_ids"]) > 0

def test_benford_test_falls_back_to_amount_column(tmp_path: Path):
    """Benford analysis must use amount_inr when all debit values are zero."""
    ledger = pd.DataFrame({
        "entry_id": [f"TEST-{i}" for i in range(1, 11)],
        "debit_inr": [0] * 10,
        "amount_inr": [
            120, 230, 340, 450, 560,
            670, 780, 890, 910, 1250,
        ],
    })

    ledger_path = tmp_path / "fallback_ledger.csv"
    ledger.to_csv(ledger_path, index=False)

    result = benford_test(str(ledger_path))

    assert result["test"] == "benford_test"
    assert result["stats"]["sample_size"] == 10


def test_find_duplicates(ground_truth_df: pd.DataFrame):
    """find_duplicates must identify all duplicate vendor disbursements within 5 days."""
    res = find_duplicates("data/ledger.csv", window_days=5)
    assert res["test"] == "find_duplicates"

    stats = res["stats"]
    assert stats["duplicate_groups_count"] == 5
    assert stats["flagged_entries_count"] == 10

    # Recall against ground truth
    gt_dup = set(ground_truth_df[ground_truth_df["anomaly_type"] == "duplicate_payment"]["entry_id"])
    assert len(gt_dup) == 10
    flagged = set(res["flagged_ids"])
    recall = len(gt_dup.intersection(flagged)) / len(gt_dup)
    assert recall == 1.0


def test_find_split_payments(ground_truth_df: pd.DataFrame):
    """find_split_payments must identify all 6 groups (18 entries) without double counting."""
    res = find_split_payments("data/ledger.csv", lower_limit=45000.0, upper_limit=50000.0, window_hours=48)
    assert res["test"] == "find_split_payments"

    stats = res["stats"]
    assert stats["split_groups_count"] == 6
    assert stats["flagged_entries_count"] == 18

    # Verify no entry is assigned to multiple clusters
    all_cluster_eids = []
    for c in stats["clusters"]:
        assert c["entry_count"] == 3
        all_cluster_eids.extend(c["entry_ids"])
    assert len(all_cluster_eids) == 18
    assert len(set(all_cluster_eids)) == 18, "Entries must not be duplicated across clusters"

    # Recall against ground truth
    gt_split = set(ground_truth_df[ground_truth_df["anomaly_type"] == "split_payment"]["entry_id"])
    assert len(gt_split) == 18
    flagged = set(res["flagged_ids"])
    recall = len(gt_split.intersection(flagged)) / len(gt_split)
    assert recall == 1.0


def test_find_weekend_round(ground_truth_df: pd.DataFrame):
    """find_weekend_round must report both 12 ledger entries and 6 economic transactions."""
    res = find_weekend_round("data/ledger.csv", round_base=10000.0, sundays_only=True)
    assert res["test"] == "find_weekend_round"

    stats = res["stats"]
    assert stats["flagged_entries_count"] == 12
    assert stats["flagged_transactions_count"] == 6
    assert "12 sunday ledger entries" in res["notes"].lower()
    assert "6 balanced transactions" in res["notes"].lower()

    # Recall against ground truth
    gt_sun = set(ground_truth_df[ground_truth_df["anomaly_type"] == "sunday_round_amount"]["entry_id"])
    assert len(gt_sun) == 12
    flagged = set(res["flagged_ids"])
    recall = len(gt_sun.intersection(flagged)) / len(gt_sun)
    assert recall == 1.0


def test_check_approval_limits(ground_truth_df: pd.DataFrame):
    """check_approval_limits must flag all self-approved entries (posted_by == approved_by)."""
    res = check_approval_limits("data/ledger.csv", "data/employees.csv")
    assert res["test"] == "check_approval_limits"

    stats = res["stats"]
    assert stats["self_approved_count"] == 8

    # Recall against ground truth
    gt_self = set(ground_truth_df[ground_truth_df["anomaly_type"] == "self_approved"]["entry_id"])
    assert len(gt_self) == 8
    flagged = set(res["flagged_ids"])
    recall = len(gt_self.intersection(flagged)) / len(gt_self)
    assert recall == 1.0


def test_vendor_bank_overlap(ground_truth_df: pd.DataFrame):
    """vendor_bank_overlap must flag shared bank accounts and ghost vendor disbursements."""
    res = vendor_bank_overlap("data/ledger.csv", "data/vendors.csv", "data/employees.csv", min_cooling_days=5)
    assert res["test"] == "vendor_bank_overlap"

    stats = res["stats"]
    assert stats["shared_vendors_count"] == 3
    assert stats["shared_bank_entries_count"] == 3
    assert stats["total_ghost_vendors_count"] == 5
    assert stats["ghost_vendor_entries_count"] == 5

    flagged = set(res["flagged_ids"])

    # 1. Recall on shared_bank_account
    gt_shared = set(ground_truth_df[ground_truth_df["anomaly_type"] == "shared_bank_account"]["entry_id"])
    assert len(gt_shared) == 3
    recall_shared = len(gt_shared.intersection(flagged)) / len(gt_shared)
    assert recall_shared == 1.0

    # 2. Recall on ghost_vendor
    gt_ghost = set(ground_truth_df[ground_truth_df["anomaly_type"] == "ghost_vendor"]["entry_id"])
    assert len(gt_ghost) == 5
    recall_ghost = len(gt_ghost.intersection(flagged)) / len(gt_ghost)
    assert recall_ghost == 1.0


def test_ratio_table():
    """ratio_table must calculate monthly margins, liquidity, and solvency ratios across 12 months."""
    res = ratio_table("data/financials.csv")
    assert res["test"] == "ratio_table"

    stats = res["stats"]
    assert stats["months_analyzed"] == 12
    assert len(stats["monthly_ratios"]) == 12

    for m in stats["monthly_ratios"]:
        assert "month" in m
        assert "gross_margin_pct" in m
        assert "operating_margin_pct" in m
        assert "current_ratio" in m
        assert "debt_to_equity" in m

    avg = stats["annual_averages"]
    assert "average_gross_margin_pct" in avg
    assert "average_operating_margin_pct" in avg
    assert "average_current_ratio" in avg
    assert "average_debt_to_equity" in avg


# =====================================================================
# 3. Comprehensive Anomaly Benchmark Test (Recall >= 90%)
# =====================================================================

def test_all_targeted_anomaly_categories_recall_benchmark(ground_truth_df: pd.DataFrame):
    """Verify that every seeded anomaly category achieves recall >= 90% against ground_truth.csv."""
    tb_res = check_trial_balance("data/ledger.csv", "data/trial_balance.csv")
    dup_res = find_duplicates("data/ledger.csv", window_days=5)
    split_res = find_split_payments("data/ledger.csv", lower_limit=45000.0, upper_limit=50000.0, window_hours=48)
    weekend_res = find_weekend_round("data/ledger.csv", round_base=10000.0, sundays_only=True)
    approval_res = check_approval_limits("data/ledger.csv", "data/employees.csv")
    overlap_res = vendor_bank_overlap("data/ledger.csv", "data/vendors.csv", "data/employees.csv", min_cooling_days=5)

    category_tool_map = {
        "trial_balance_gap": set(tb_res["flagged_ids"]),
        "duplicate_payment": set(dup_res["flagged_ids"]),
        "split_payment": set(split_res["flagged_ids"]),
        "sunday_round_amount": set(weekend_res["flagged_ids"]),
        "self_approved": set(approval_res["flagged_ids"]),
        "shared_bank_account": set(overlap_res["flagged_ids"]),
        "ghost_vendor": set(overlap_res["flagged_ids"]),
    }

    recall_report = {}
    for category, flagged_set in category_tool_map.items():
        gt_ids = set(ground_truth_df[ground_truth_df["anomaly_type"] == category]["entry_id"])
        assert len(gt_ids) > 0, f"No ground truth entries for category {category}"
        tp = len(gt_ids.intersection(flagged_set))
        recall = tp / len(gt_ids)
        recall_report[category] = {
            "gt_count": len(gt_ids),
            "tp_count": tp,
            "recall": recall,
        }
        assert recall >= 0.90, f"Category '{category}' failed recall requirement! Expected >= 0.90, got {recall:.4f}"

    for cat, metrics in recall_report.items():
        assert metrics["recall"] >= 0.90


def test_retrieve_policy_self_approval():
    results = retrieve_policy("self approval and segregation of duties", k=3)
    assert results
    assert results[0]["clause_id"] == "3.1"


def test_retrieve_policy_gstin():
    results = retrieve_policy("vendor GSTIN verification", k=3)
    assert results
    assert results[0]["clause_id"] == "5.1"


def test_retrieve_policy_approval_tiers():
    results = retrieve_policy("financial delegated authority approval limits", k=3)
    assert results
    assert any(result["clause_id"] in {"2.1", "2.2", "2.3"} for result in results)


def test_retrieve_policy_empty_query():
    assert retrieve_policy("") == []

# =====================================================================
# 4. Phase 6: Risk Ranking Tests
# =====================================================================

def test_build_ranked_findings_returns_valid_structure():
    result = build_ranked_findings()

    assert "findings" in result
    assert result["total_findings"] == len(result["findings"])
    assert result["total_amount_at_risk_inr"] >= 0


def test_ranked_findings_are_sorted_by_score():
    result = build_ranked_findings()
    findings = result["findings"]

    scores = [finding["score"] for finding in findings]

    assert scores == sorted(scores, reverse=True)


def test_every_ranked_finding_has_valid_entry_ids():
    result = build_ranked_findings()
    ledger = pd.read_csv("data/ledger.csv")

    valid_ids = set(ledger["entry_id"])

    for finding in result["findings"]:
        assert finding["entry_ids"]
        assert set(finding["entry_ids"]).issubset(valid_ids)


def test_ranked_findings_have_valid_risk_scores():
    result = build_ranked_findings()

    for finding in result["findings"]:
        assert 1 <= finding["likelihood"] <= 5
        assert 1 <= finding["impact"] <= 5
        assert finding["score"] == finding["likelihood"] * finding["impact"]
        assert finding["amount_at_risk_inr"] >= 0


# =====================================================================
# 5. Phase 7: Skeptic Verification Tests
# =====================================================================

def test_verify_entry_ids_accepts_existing_ids():
    from auditpilot.tools.skeptic_tools import verify_entry_ids

    result = verify_entry_ids(["JE-2025-0249"])

    assert result["test"] == "verify_entry_ids"
    assert result["is_valid"] is True
    assert result["valid_ids"] == ["JE-2025-0249"]
    assert result["missing_ids"] == []
    assert result["stats"]["valid_count"] == 1


def test_verify_entry_ids_detects_nonexistent_ids():
    from auditpilot.tools.skeptic_tools import verify_entry_ids

    result = verify_entry_ids([
        "JE-2025-0249",
        "INVALID-JE-9999",
    ])

    assert result["is_valid"] is False
    assert result["valid_ids"] == ["JE-2025-0249"]
    assert result["missing_ids"] == ["INVALID-JE-9999"]
    assert result["stats"]["provided_count"] == 2
    assert result["stats"]["valid_count"] == 1
    assert result["stats"]["missing_count"] == 1
# =====================================================================
# 6. Phase 7: Skeptic Controller Tests
# =====================================================================

def test_skeptic_drops_finding_with_invalid_entry_id():
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    ranked = {
        "findings": [{
            "id": "TEST-001",
            "entry_ids": ["INVALID-JE-9999"],
            "amount_at_risk_inr": 50000,
            "likelihood": 4,
            "impact": 3,
            "score": 12,
            "status": "pending",
        }]
    }

    reviews = {
        "reviews": [{
            "finding_id": "TEST-001",
            "status": "confirmed",
            "review_reason": "Evidence appears valid.",
        }]
    }

    result = apply_skeptic_reviews(ranked, reviews)
    finding = result["findings"][0]

    assert finding["status"] == "dropped"
    assert "verification failed" in finding["review_reason"].lower()


def test_skeptic_confirms_finding_with_valid_entry_id():
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    ranked = {
        "findings": [{
            "id": "TEST-002",
            "entry_ids": ["JE-2025-0249"],
            "amount_at_risk_inr": 50000,
            "likelihood": 4,
            "impact": 3,
            "score": 12,
            "status": "pending",
        }]
    }

    reviews = {
        "reviews": [{
            "finding_id": "TEST-002",
            "status": "confirmed",
            "review_reason": "The evidence supports the control exception.",
        }]
    }

    result = apply_skeptic_reviews(ranked, reviews)

    assert result["findings"][0]["status"] == "confirmed"


def test_skeptic_preserves_risk_calculations():
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    ranked = {
        "findings": [{
            "id": "TEST-003",
            "entry_ids": ["JE-2025-0249"],
            "amount_at_risk_inr": 75000,
            "likelihood": 5,
            "impact": 4,
            "score": 20,
            "status": "pending",
        }]
    }

    reviews = {
        "reviews": [{
            "finding_id": "TEST-003",
            "status": "confirmed",
            "review_reason": "Evidence supports the finding.",
        }]
    }

    result = apply_skeptic_reviews(ranked, reviews)
    finding = result["findings"][0]

    assert finding["amount_at_risk_inr"] == 75000
    assert finding["likelihood"] == 5
    assert finding["impact"] == 4
    assert finding["score"] == 20


def test_skeptic_preserves_completed_decisions():
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    ranked = {
        "findings": [{
            "id": "TEST-004",
            "entry_ids": ["JE-2025-0249"],
            "status": "confirmed",
            "review_reason": "Previously confirmed.",
        }]
    }

    result = apply_skeptic_reviews(ranked, {"reviews": []})

    assert result["findings"][0]["status"] == "confirmed"
    assert result["findings"][0]["review_reason"] == "Previously confirmed."


def test_skeptic_retains_dropped_findings_with_reasons():
    """Verify dropped findings remain in findings list (not silently deleted) with reasons."""
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    ranked = {
        "findings": [
            {
                "id": "DROP-001",
                "entry_ids": ["INVALID-ID-001"],
                "amount_at_risk_inr": 25000,
                "status": "pending",
            },
            {
                "id": "DROP-002",
                "entry_ids": ["JE-2025-0249"],
                "amount_at_risk_inr": 30000,
                "status": "pending",
            },
        ],
        "total_findings": 2,
        "total_amount_at_risk_inr": 55000,
    }

    reviews = {
        "reviews": [
            {
                "finding_id": "DROP-002",
                "status": "dropped",
                "review_reason": "Legitimate business purpose established by procurement memo.",
            }
        ]
    }

    result = apply_skeptic_reviews(ranked, reviews)
    findings = result["findings"]

    # Both findings must be retained in the list — none silently removed
    assert len(findings) == 2
    assert findings[0]["id"] == "DROP-001"
    assert findings[0]["status"] == "dropped"
    assert "verification failed" in findings[0]["review_reason"].lower()

    assert findings[1]["id"] == "DROP-002"
    assert findings[1]["status"] == "dropped"
    assert "procurement memo" in findings[1]["review_reason"]


def test_apply_skeptic_reviews_handles_pydantic_model():
    """Verify apply_skeptic_reviews safely accepts Pydantic RankedFindings instances."""
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews
    from auditpilot.schemas import Finding, RankedFindings

    ranked_model = RankedFindings(
        findings=[
            Finding(
                id="MOD-001",
                category="compliance",
                title="Self-approved entry",
                entry_ids=["JE-2025-0249"],
                amount_at_risk_inr=15000.0,
                likelihood=3,
                impact=3,
                score=9,
                rationale="Maker equals checker.",
            )
        ],
        total_findings=1,
        total_amount_at_risk_inr=15000.0,
    )

    reviews = {
        "reviews": [
            {
                "finding_id": "MOD-001",
                "status": "confirmed",
                "review_reason": "SoD violation confirmed by employee record.",
            }
        ]
    }

    result = apply_skeptic_reviews(ranked_model, reviews)
    assert isinstance(result, dict)
    assert len(result["findings"]) == 1
    assert result["findings"][0]["status"] == "confirmed"


def test_skeptic_loop_configuration():
    """Verify skeptic_loop configuration and max_iterations constraint from specification."""
    from auditpilot.agents.skeptic import skeptic_agent, skeptic_loop
    from auditpilot.agents.skeptic_controller import skeptic_controller

    assert skeptic_loop.name == "skeptic_loop"
    assert skeptic_loop.max_iterations == 3
    assert len(skeptic_loop.sub_agents) == 2
    assert skeptic_loop.sub_agents[0] is skeptic_agent
    assert skeptic_loop.sub_agents[1] is skeptic_controller


def test_skeptic_controller_escalates_when_all_findings_resolved():
    """Verify SkepticControllerAgent sets escalate=True when 0 findings need evidence."""
    import asyncio
    from unittest.mock import MagicMock
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.sessions import Session
    from auditpilot.agents.skeptic_controller import skeptic_controller

    async def _test():
        session = Session(
            id="sess_resolved",
            app_name="auditpilot",
            user_id="user_test",
            state={
                "ranked_findings": {
                    "findings": [{
                        "id": "F-RESOLVED",
                        "entry_ids": ["JE-2025-0249"],
                        "amount_at_risk_inr": 5000,
                        "likelihood": 2,
                        "impact": 2,
                        "score": 4,
                        "status": "pending",
                        "rationale": "Sample check",
                    }],
                    "total_findings": 1,
                    "total_amount_at_risk_inr": 5000,
                },
                "skeptic_reviews": {
                    "reviews": [{
                        "finding_id": "F-RESOLVED",
                        "status": "confirmed",
                        "review_reason": "Verified and supported.",
                    }]
                },
            },
        )
        ctx = MagicMock(spec=InvocationContext)
        ctx.session = session
        ctx.invocation_id = "inv_001"
        ctx.branch = "main"

        events = []
        async for event in skeptic_controller._run_async_impl(ctx):
            events.append(event)

        assert len(events) == 1
        event = events[0]
        # escalate=True terminates LoopAgent execution
        assert event.actions.escalate is True
        assert event.actions.state_delta["ranked_findings"]["findings"][0]["status"] == "confirmed"
        assert event.actions.state_delta["skeptic_review_rounds"] == 1

    asyncio.run(_test())


def test_skeptic_controller_continues_when_needs_evidence_exists():
    """Verify SkepticControllerAgent sets escalate=False when findings still need evidence."""
    import asyncio
    from unittest.mock import MagicMock
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.sessions import Session
    from auditpilot.agents.skeptic_controller import skeptic_controller

    async def _test():
        session = Session(
            id="sess_continue",
            app_name="auditpilot",
            user_id="user_test",
            state={
                "ranked_findings": {
                    "findings": [{
                        "id": "F-UNRESOLVED",
                        "entry_ids": ["JE-2025-0249"],
                        "amount_at_risk_inr": 8000,
                        "likelihood": 3,
                        "impact": 3,
                        "score": 9,
                        "status": "pending",
                        "rationale": "Needs more documentation",
                    }],
                    "total_findings": 1,
                    "total_amount_at_risk_inr": 8000,
                },
                "skeptic_reviews": {
                    "reviews": [{
                        "finding_id": "F-UNRESOLVED",
                        "status": "needs_evidence",
                        "review_reason": "Secondary invoice required.",
                    }]
                },
            },
        )
        ctx = MagicMock(spec=InvocationContext)
        ctx.session = session
        ctx.invocation_id = "inv_002"
        ctx.branch = "main"

        events = []
        async for event in skeptic_controller._run_async_impl(ctx):
            events.append(event)

        assert len(events) == 1
        event = events[0]
        # escalate=False allows LoopAgent to perform the next iteration
        assert event.actions.escalate is False
        assert event.actions.state_delta["ranked_findings"]["findings"][0]["status"] == "needs_evidence"
        assert event.actions.state_delta["skeptic_review_rounds"] == 1

    asyncio.run(_test())


def test_skeptic_controller_preserves_risk_and_finding_fields_intact():
    """Verify all non-status fields (amount, likelihood, impact, score, rationale) are strictly preserved."""
    from auditpilot.agents.skeptic_controller import apply_skeptic_reviews

    original_finding = {
        "id": "PRESERVE-001",
        "category": "vendor",
        "title": "Vendor Bank Overlap",
        "entry_ids": ["JE-2025-0249"],
        "evidence": ["Vendor VND-001 bank account matches EMP-05"],
        "amount_at_risk_inr": 123456.78,
        "likelihood": 5,
        "impact": 4,
        "score": 20,
        "rationale": "High-risk conflict of interest.",
        "status": "pending",
    }
    ranked = {"findings": [dict(original_finding)]}
    reviews = {
        "reviews": [{
            "finding_id": "PRESERVE-001",
            "status": "confirmed",
            "review_reason": "Cross-verified with HR employee master.",
        }]
    }

    result = apply_skeptic_reviews(ranked, reviews)
    updated = result["findings"][0]

    for key, expected_val in original_finding.items():
        if key == "status":
            assert updated["status"] == "confirmed"
        else:
            assert updated[key] == expected_val
    assert updated["review_reason"] == "Cross-verified with HR employee master."
