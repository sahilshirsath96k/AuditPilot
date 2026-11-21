"""Audit reporting and memorandum drafting agent for AuditPilot."""

from collections.abc import Callable
from typing import AsyncGenerator
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from auditpilot.tools.report_tools import format_audit_memo, write_audit_memo


class ReportAgent(BaseAgent):
    """Generates the formal 7-section Audit Memorandum deterministically in DRAFT status."""

    tools: list[Callable] = [write_audit_memo]
    output_key: str = "audit_memo_output"

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state if ctx.session else {}

        data_profile = state.get("data_profile", {})
        ranked_findings = state.get("ranked_findings", {})

        if hasattr(data_profile, "model_dump"):
            data_profile = data_profile.model_dump()
        if hasattr(ranked_findings, "model_dump"):
            ranked_findings = ranked_findings.model_dump()

        # Strict fail-closed check: Never generate a report if data intake failed
        status = data_profile.get("status") if isinstance(data_profile, dict) else None
        status = getattr(status, "value", status)
        status = str(status).upper() if status else "MISSING"

        if status not in {"PASSED", "PASSED_WITH_VARIANCE"}:
            err_msg = (
                f"Report generation halted: Data intake status is '{status}'. "
                "A formal audit memorandum cannot be drafted on an unverified or corrupted dataset."
            )
            yield Event(
                author=self.name,
                invocation_id=ctx.invocation_id,
                branch=ctx.branch,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=err_msg)],
                ),
            )
            return

        # Deterministically format the complete audit memorandum
        # Strictly DRAFT: report_agent NEVER approves its own report
        memo_content = format_audit_memo(
            data_profile=data_profile,
            ranked_findings=ranked_findings,
            status="DRAFT",
        )

        # Write to docs/audit_memo.md
        memo_res = write_audit_memo(
            markdown_content=memo_content,
            status="DRAFT",
            output_path="docs/audit_memo.md",
        )

        findings_list = ranked_findings.get("findings", []) if isinstance(ranked_findings, dict) else []
        confirmed_count = sum(1 for f in findings_list if f.get("status") == "confirmed")
        needs_evidence_count = sum(1 for f in findings_list if f.get("status") == "needs_evidence")
        dropped_count = sum(1 for f in findings_list if f.get("status") == "dropped")

        summary_msg = (
            "Audit Memorandum successfully generated at docs/audit_memo.md (Status: DRAFT).\n\n"
            f"- Confirmed findings: {confirmed_count}\n"
            f"- Findings needing additional evidence: {needs_evidence_count}\n"
            f"- Dropped findings (in Appendix): {dropped_count}\n\n"
            "HUMAN SIGN-OFF REQUIRED:\n"
            "The audit memorandum is currently in DRAFT status awaiting partner review.\n"
            "An authorized Audit Partner must review docs/audit_memo.md and issue a sign-off decision:\n"
            "- 'APPROVE' to finalize and sign off on the memorandum.\n"
            "- 'REQUEST_CHANGES' with comments to request adjustments.\n"
            "- 'REJECT' with justification to reject the memorandum."
        )

        yield Event(
            author=self.name,
            invocation_id=ctx.invocation_id,
            branch=ctx.branch,
            actions=EventActions(
                state_delta={
                    "audit_memo_status": "DRAFT",
                    "audit_memo_path": memo_res["path"],
                    "audit_memo_bytes": memo_res["bytes_written"],
                }
            ),
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=summary_msg)],
            ),
        )


report_agent = ReportAgent(
    name="report_agent",
    description="Synthesizes the comprehensive Audit Memorandum at docs/audit_memo.md in DRAFT status awaiting partner sign-off.",
)
