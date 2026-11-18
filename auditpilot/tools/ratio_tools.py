"""Financial ratio analysis tools for evaluating liquidity, profitability, and solvency trends."""

from pathlib import Path
from typing import Any
import pandas as pd


def ratio_table(financials_path: str = "data/financials.csv") -> dict[str, Any]:
    """Compute monthly liquidity, profitability, and leverage ratios from financial statements.

    Analyzes monthly income statement and balance sheet records from financials.csv to derive:
    1. Gross Margin: (revenue_inr - cogs_inr) / revenue_inr
    2. Operating Margin: (revenue_inr - cogs_inr - opex_inr) / revenue_inr
    3. Current Ratio: (cash_inr + receivables_inr) / payables_inr
    4. Debt-to-Equity Ratio: total_liabilities_inr / (total_assets_inr - total_liabilities_inr)

    Args:
        financials_path: Path to the monthly financials CSV file.

    Returns:
        A dictionary with keys:
            - test: Name of the audit test ('ratio_table').
            - flagged_ids: List of anomalous months (e.g., negative margin or distressed liquidity).
            - stats: Monthly ratio records, annual averages, and trend evaluations.
            - notes: Executive financial health and performance summary.
    """
    path = Path(financials_path)
    if not path.exists():
        return {
            "test": "ratio_table",
            "flagged_ids": [],
            "stats": {"file_exists": False},
            "notes": f"Financials file not found at path: {financials_path}",
        }

    fin = pd.read_csv(path)
    required_cols = [
        "month",
        "revenue_inr",
        "cogs_inr",
        "opex_inr",
        "cash_inr",
        "receivables_inr",
        "payables_inr",
        "total_assets_inr",
        "total_liabilities_inr",
    ]
    missing = [c for c in required_cols if c not in fin.columns]
    if missing:
        return {
            "test": "ratio_table",
            "flagged_ids": [],
            "stats": {"missing_columns": missing},
            "notes": f"Financials missing required columns: {missing}",
        }

    monthly_records = []
    flagged_months: list[str] = []

    for _, row in fin.iterrows():
        m = str(row["month"])
        rev = float(row["revenue_inr"])
        cogs = float(row["cogs_inr"])
        opex = float(row["opex_inr"])
        cash = float(row["cash_inr"])
        recv = float(row["receivables_inr"])
        pay = float(row["payables_inr"])
        assets = float(row["total_assets_inr"])
        liab = float(row["total_liabilities_inr"])

        equity = assets - liab

        # Ratios
        gross_margin = (rev - cogs) / rev if rev > 0 else 0.0
        operating_margin = (rev - cogs - opex) / rev if rev > 0 else 0.0
        current_ratio = (cash + recv) / pay if pay > 0 else 0.0
        debt_to_equity = liab / equity if equity > 0 else 0.0

        is_anomalous = operating_margin < 0 or current_ratio < 1.0
        if is_anomalous:
            flagged_months.append(m)

        monthly_records.append(
            {
                "month": m,
                "revenue_inr": rev,
                "gross_margin_pct": round(gross_margin * 100, 2),
                "operating_margin_pct": round(operating_margin * 100, 2),
                "current_ratio": round(current_ratio, 2),
                "debt_to_equity": round(debt_to_equity, 2),
                "working_capital_inr": round((cash + recv) - pay, 2),
                "is_distressed": is_anomalous,
            }
        )

    # Compute full-year averages
    rdf = pd.DataFrame(monthly_records)
    avg_gm = round(float(rdf["gross_margin_pct"].mean()), 2)
    avg_om = round(float(rdf["operating_margin_pct"].mean()), 2)
    avg_cr = round(float(rdf["current_ratio"].mean()), 2)
    avg_de = round(float(rdf["debt_to_equity"].mean()), 2)

    stats = {
        "months_analyzed": int(len(fin)),
        "annual_averages": {
            "average_gross_margin_pct": avg_gm,
            "average_operating_margin_pct": avg_om,
            "average_current_ratio": avg_cr,
            "average_debt_to_equity": avg_de,
        },
        "flagged_distressed_months": flagged_months,
        "monthly_ratios": monthly_records,
    }

    notes = (
        f"Financial Ratio Analysis ({len(fin)} months): Average Gross Margin: {avg_gm}%, "
        f"Average Operating Margin: {avg_om}%, Average Current Ratio: {avg_cr:.2f}, "
        f"Average Debt-to-Equity: {avg_de:.2f}. Identified {len(flagged_months)} months with "
        f"liquidity pressure (Current Ratio < 1.0) or negative operating margin."
    )

    return {
        "test": "ratio_table",
        "flagged_ids": flagged_months,
        "stats": stats,
        "notes": notes,
    }
