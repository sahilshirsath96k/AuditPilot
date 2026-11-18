"""Deterministic Data Intake Agent for AuditPilot.

Inspects accounting datasets, verifies schemas, numeric validity, dates,
row counts, double-entry mathematical balance, and reconciles trial balance.
"""

from typing import AsyncGenerator, Callable
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from auditpilot.schemas import DataProfile, build_data_profile
from auditpilot.tools.data_tools import load_ledger
from auditpilot.tools.reconciliation import check_trial_balance


class IntakeAgent(BaseAgent):
    """Deterministic intake agent performing accounting file verification and trial balance reconciliation."""

    tools: list[Callable] = [load_ledger, check_trial_balance]
    output_schema: type = DataProfile
    output_key: str = "data_profile"

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Execute deterministic load_ledger and check_trial_balance and build DataProfile in pure Python."""
        ledger_path = "data/ledger.csv"
        tb_path = "data/trial_balance.csv"

        # Inspect session state for custom file paths
        state = ctx.session.state if ctx.session else {}
        if state.get("ledger_path"):
            ledger_path = state["ledger_path"]
        if state.get("trial_balance_path"):
            tb_path = state["trial_balance_path"]

        # Also inspect user input content for custom CSV paths if present
        if ctx.user_content and ctx.user_content.parts:
            user_text = " ".join([p.text for p in ctx.user_content.parts if p.text])
            for token in user_text.split():
                token_clean = token.strip("',\"();")
                if token_clean.endswith(".csv"):
                    if "trial" in token_clean.lower() or "tb" in token_clean.lower():
                        tb_path = token_clean
                    else:
                        ledger_path = token_clean

        # Deterministic tool executions (pure Python, zero LLM estimation)
        ledger_res = load_ledger(ledger_path=ledger_path)
        tb_res = check_trial_balance(ledger_path=ledger_path, tb_path=tb_path)

        # Deterministic Python profiling and fail-closed status classification
        profile = build_data_profile(ledger_res=ledger_res, tb_res=tb_res)

        gap_str = (
            f"Rs {profile.trial_balance_gap_inr:,.2f}"
            if profile.trial_balance_gap_inr is not None
            else "N/A"
        )
        summary_text = (
            f"Data Intake Status: {profile.status}\n"
            f"Rows: {profile.row_count}, Columns: {profile.column_count}\n"
            f"Double-entry Balanced: {profile.is_balanced}\n"
            f"Trial Balance Reconciled: {profile.trial_balance_reconciled}\n"
            f"Discrepancy Gap: {gap_str}\n"
            f"Flagged Entry IDs: {profile.flagged_ids}\n"
            f"Notes: {profile.notes}"
        )

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            actions=EventActions(state_delta={"data_profile": profile.model_dump()}),
            content=types.Content(role="model", parts=[types.Part.from_text(text=summary_text)]),
        )


intake_agent = IntakeAgent(
    name="intake_agent",
    description="Validates accounting dataset structure, verifies double-entry balance, and reconciles trial balance.",
)
