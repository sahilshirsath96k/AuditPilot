"""Lifecycle callbacks, pipeline guards, and security audit guardrails for AuditPilot agents."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# Regex matching Indian bank account numbers (11 to 18 digits)
# Protects against decimal amounts (e.g. 171175194.18) and word boundaries.
BANK_ACCOUNT_PATTERN = re.compile(r"(?<![\d\w])(\d{11,18})(?![\d\w]|(?:\.\d))")

# Pattern detecting sensitive secret keys
SENSITIVE_KEY_PATTERN = re.compile(
    r"(key|secret|token|password|credential|auth|api_key)",
    re.IGNORECASE,
)
# Detect common secrets embedded directly in free-text log values.
SECRET_VALUE_PATTERNS = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)\b(?:AIza[0-9A-Za-z_-]{20,}|"
        r"sk-[A-Za-z0-9_-]{16,}|"
        r"gh[pousr]_[A-Za-z0-9]{20,}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    re.compile(
        r"""(?i)\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret)"""
        r"""\s*[:=]\s*['"]?[^\s,'" ;]+"""
    ),
]


def mask_bank_accounts(text: str) -> str:
    """Mask 11 to 18 digit bank account numbers before prompts reach the LLM.

    Replaces matched bank accounts with '[REDACTED_ACCOUNT_****XXXX]' where
    XXXX is the last 4 digits of the account number. Preserves transaction
    amounts, dates, entry IDs, and account codes.

    Args:
        text: Raw input text.

    Returns:
        Sanitized text with bank account numbers redacted.
    """
    if not text:
        return ""
    return BANK_ACCOUNT_PATTERN.sub(
        lambda m: f"[REDACTED_ACCOUNT_****{m.group(1)[-4:]}]",
        str(text),
    )

def sanitize_secrets_and_pii(data: Any) -> Any:
    """Recursively scrub secrets and mask bank accounts in structured data."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if SENSITIVE_KEY_PATTERN.search(str(k)):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = sanitize_secrets_and_pii(v)
        return sanitized

    elif isinstance(data, list):
        return [sanitize_secrets_and_pii(item) for item in data]

    elif isinstance(data, str):
        sanitized = mask_bank_accounts(data)

        for pattern in SECRET_VALUE_PATTERNS:
            sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)

        return sanitized

    return data


def log_audit_trail_event(
    agent_name: str,
    event_type: str,
    tool_name: str | None = None,
    args_summary: Any = None,
    result_data: Any = None,
    log_path: str | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Append one structured JSON line per model or tool execution to audit_trail.jsonl.

    Enforces provenance tracking with ISO-8601 UTC timestamps, agent and tool
    identities, argument summaries stripped of secrets and PII, and canonical
    SHA-256 result checksums.

    Args:
        agent_name: Name of the initiating agent.
        event_type: 'model_call' or 'tool_call'.
        tool_name: Name of tool if event_type is 'tool_call'.
        args_summary: Arguments passed to model or tool.
        result_data: Payload or response data to be cryptographically hashed.
        log_path: Target log file path (defaults to AUDIT_TRAIL_LOG_PATH or 'audit_trail.jsonl').
        timestamp: Optional explicit timestamp string for deterministic offline testing.

    Returns:
        The logged event dictionary.
    """
    target_path = log_path or os.getenv("AUDIT_TRAIL_LOG_PATH", "audit_trail.jsonl")
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sanitize arguments and results to guarantee zero secret or raw PII leakage
    clean_args = sanitize_secrets_and_pii(args_summary) if args_summary is not None else {}
    clean_result = sanitize_secrets_and_pii(result_data) if result_data is not None else {}

    # Canonical JSON serialization before calculating SHA-256 hash
    try:
        canonical_bytes = json.dumps(
            clean_result,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        result_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    except Exception:
        result_sha256 = hashlib.sha256(b"").hexdigest()

    event = {
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "agent_name": agent_name or "audit_lead",
        "event_type": event_type,
        "tool_name": tool_name or "",
        "args_summary": clean_args,
        "result_sha256": result_sha256,
    }

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return event


def before_model_guardrail(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
    **kwargs: Any,
) -> LlmResponse | None:
    """Pre-model callback: masks bank accounts in-place and logs model call provenance.

    Args:
        callback_context: ADK callback invocation context.
        llm_request: The prepared request object to be sent to Gemini.

    Returns:
        None to permit the model request to proceed normally.
    """
    agent_name = getattr(callback_context, "agent_name", None) or "audit_agent"

    # Redact bank account numbers across all text parts in the request
    if hasattr(llm_request, "contents") and llm_request.contents:
        for content in llm_request.contents:
            if hasattr(content, "parts") and content.parts:
                for part in content.parts:
                    if hasattr(part, "text") and part.text:
                        part.text = mask_bank_accounts(part.text)

    # Log model call event to append-only audit trail
    last_prompt = ""
    if hasattr(llm_request, "contents") and llm_request.contents:
        last_turn = llm_request.contents[-1]
        if hasattr(last_turn, "parts") and last_turn.parts:
            last_prompt = last_turn.parts[0].text or ""

    log_audit_trail_event(
        agent_name=agent_name,
        event_type="model_call",
        tool_name=None,
        args_summary={"turns": len(getattr(llm_request, "contents", []))},
        result_data=last_prompt,
    )

    return None


def after_tool_audit_logger(
    tool: BaseTool,
    tool_args: dict[str, Any],
    tool_context: ToolContext,
    result: dict[str, Any],
    **kwargs: Any,
) -> None:
    """Log ADK tool execution provenance without exposing raw results."""
    tool_name = getattr(tool, "name", None) or getattr(tool, "__name__", type(tool).__name__)
    agent_name = getattr(tool_context, "agent_name", None) or "audit_specialist"

    log_audit_trail_event(
        agent_name=agent_name,
        event_type="tool_call",
        tool_name=tool_name,
        args_summary=tool_args,
        result_data=result,
    )

    return None


def pipeline_guard(callback_context: CallbackContext) -> types.Content | None:
    """Pre-execution pipeline guard for downstream audit agents.

    Inspects session state for 'data_profile'. If data intake failed (e.g. missing
    files, unreadable CSVs, or missing required columns), short-circuits downstream
    agent execution and returns an informative diagnostic message.

    Args:
        callback_context: The invocation context containing session state.

    Returns:
        types.Content containing the halt diagnostic if data intake failed,
        or None to permit downstream agent execution.
    """
    state = callback_context.state

    data_profile = state.get("data_profile")
    if not data_profile:
        return None

    status = (
        data_profile.get("status")
        if isinstance(data_profile, dict)
        else getattr(data_profile, "status", None)
    )

    if status == "FAILED":
        raw_reasons = (
            data_profile.get("failure_reasons", [])
            if isinstance(data_profile, dict)
            else getattr(data_profile, "failure_reasons", [])
        )
        reasons_str = "; ".join(raw_reasons) if raw_reasons else "Data intake validation failed"
        notes = (
            data_profile.get("notes", "")
            if isinstance(data_profile, dict)
            else getattr(data_profile, "notes", "")
        )

        diagnostic_text = (
            f"AUDIT PIPELINE HALTED: Data intake validation failed.\n"
            f"Failure Reasons: {reasons_str}\n"
            f"Notes: {notes}\n"
            f"Downstream audit procedures cannot proceed on invalid or corrupted datasets. "
            f"Please rectify the data files before restarting the audit."
        )

        return types.Content(
            role="model",
            parts=[types.Part.from_text(text=diagnostic_text)],
        )

    return None
