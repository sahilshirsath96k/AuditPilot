
"""Deterministic verification tools for the skeptic agent."""

from pathlib import Path
from typing import Any

import pandas as pd


def verify_entry_ids(
    entry_ids: list[str],
    ledger_path: str = "data/ledger.csv",
) -> dict[str, Any]:
    """Verify that supplied journal entry IDs exist in the ledger."""

    if not entry_ids:
        return {
            "test": "verify_entry_ids",
            "is_valid": False,
            "valid_ids": [],
            "missing_ids": [],
            "stats": {
                "provided_count": 0,
                "valid_count": 0,
                "missing_count": 0,
            },
            "notes": "No journal entry IDs were provided.",
        }

    path = Path(ledger_path)

    if not path.is_file():
        raise FileNotFoundError(f"Ledger file not found: {path}")

    ledger = pd.read_csv(path)

    if "entry_id" not in ledger.columns:
        raise ValueError("Ledger is missing the required entry_id column.")

    if not ledger["entry_id"].notna().all():
        raise ValueError("Ledger contains missing entry_id values.")

    existing_ids = set(ledger["entry_id"].astype(str))
    supplied_ids = list(dict.fromkeys(str(item) for item in entry_ids))

    valid_ids = [item for item in supplied_ids if item in existing_ids]
    missing_ids = [item for item in supplied_ids if item not in existing_ids]

    return {
        "test": "verify_entry_ids",
        "is_valid": len(missing_ids) == 0,
        "valid_ids": valid_ids,
        "missing_ids": missing_ids,
        "stats": {
            "provided_count": len(supplied_ids),
            "valid_count": len(valid_ids),
            "missing_count": len(missing_ids),
        },
        "notes": (
            "All supplied journal entry IDs exist in the ledger."
            if not missing_ids
            else f"{len(missing_ids)} supplied journal entry ID(s) do not exist."
        ),
    }
