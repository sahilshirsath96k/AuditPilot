"""Comprehensive unit and security test suite for Phase 9: Callbacks, Audit Trail, and Guardrails."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from auditpilot.callbacks import (
    after_tool_audit_logger,
    before_model_guardrail,
    log_audit_trail_event,
    mask_bank_accounts,
    pipeline_guard,
    sanitize_secrets_and_pii,
)


# =====================================================================
# 1. Bank Account Masking Tests
# =====================================================================

def test_mask_bank_accounts_vendor_and_employee():
    """Verify that 14-digit vendor and employee bank accounts are redacted to [REDACTED_ACCOUNT_****XXXX]."""
    text = (
        "Vendor VND-001 bank account is 50200000100291. "
        "Employee EMP-01 account is 91201004567801. "
        "Another account 123456789012345 was credited."
    )
    masked = mask_bank_accounts(text)

    # Raw bank numbers must NOT appear anywhere in sanitized text
    assert "50200000100291" not in masked
    assert "91201004567801" not in masked
    assert "123456789012345" not in masked

    # Redacted tokens preserving last 4 digits MUST appear
    assert "[REDACTED_ACCOUNT_****0291]" in masked
    assert "[REDACTED_ACCOUNT_****7801]" in masked
    assert "[REDACTED_ACCOUNT_****2345]" in masked


def test_mask_bank_accounts_preserves_legitimate_figures():
    """Verify monetary amounts, dates, account codes, and journal entry IDs are NOT redacted."""
    text = (
        "Total Turnover: 171175194.18 INR. "
        "Date: 2025-04-01. "
        "Account Code: 6020. "
        "Entry ID: JE-2025-2767. "
        "Amount: 125000.00 INR. "
        "Large decimal: 12345678901.50."
    )
    masked = mask_bank_accounts(text)

    # Must preserve exact numbers
    assert "171175194.18" in masked
    assert "2025-04-01" in masked
    assert "6020" in masked
    assert "JE-2025-2767" in masked
    assert "125000.00" in masked
    assert "12345678901.50" in masked


def test_mask_bank_accounts_empty_and_none():
    """Verify graceful handling of empty or None values."""
    assert mask_bank_accounts("") == ""
    assert mask_bank_accounts(None) == ""


# =====================================================================
# 2. Secret and PII Sanitization Tests
# =====================================================================

def test_sanitize_secrets_and_pii_recursive():
    """Verify sensitive keys are scrubbed and bank accounts in strings are masked."""
    raw_data = {
        "api_key": "AIzaSySecretApiKey123",
        "nested": {
            "auth_token": "bearer-token-xyz",
            "password": "super-secret-pass",
            "vendor_note": "Payment sent to 50200000100291 for precision tools",
            "amount_inr": 48000.0,
        },
        "items": [
            {"credential": "secret_val", "bank": "91201004567801"},
            {"safe_field": "public_data"},
        ],
    }

    sanitized = sanitize_secrets_and_pii(raw_data)

    # Secrets must be scrubbed
    assert sanitized["api_key"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["auth_token"] == "[REDACTED_SECRET]"
    assert sanitized["nested"]["password"] == "[REDACTED_SECRET]"
    assert sanitized["items"][0]["credential"] == "[REDACTED_SECRET]"

    # Bank accounts must be masked
    assert "50200000100291" not in sanitized["nested"]["vendor_note"]
    assert "[REDACTED_ACCOUNT_****0291]" in sanitized["nested"]["vendor_note"]
    assert sanitized["items"][0]["bank"] == "[REDACTED_ACCOUNT_****7801]"

    # Safe fields preserved
    assert sanitized["nested"]["amount_inr"] == 48000.0
    assert sanitized["items"][1]["safe_field"] == "public_data"


def test_sanitize_secrets_embedded_in_text():
    """Verify common API keys and bearer tokens are redacted in free text."""
    from auditpilot.callbacks import sanitize_secrets_and_pii

    raw = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
        "API key: AIzaSy123456789012345678901234567890 "
        "Other text: safe"
    )

    sanitized = sanitize_secrets_and_pii(raw)

    assert "abcdefghijklmnopqrstuvwxyz123456" not in sanitized
    assert "AIzaSy123456789012345678901234567890" not in sanitized
    assert "[REDACTED_SECRET]" in sanitized
    assert "Other text: safe" in sanitized


# =====================================================================
# 3. Audit Trail Logging & Canonical SHA-256 Tests
# =====================================================================

def test_log_audit_trail_event_canonical_sha256(tmp_path: Path):
    """Verify canonical JSON serialization produces reproducible, deterministic SHA-256 hashes."""
    log_file = tmp_path / "test_audit_trail.jsonl"

    data_a = {"z_key": 1, "a_key": [2, 3], "amount": 50000.0}
    data_b = {"amount": 50000.0, "a_key": [2, 3], "z_key": 1}

    event_a = log_audit_trail_event(
        agent_name="anomaly_agent",
        event_type="tool_call",
        tool_name="find_duplicates",
        args_summary={"window_days": 5},
        result_data=data_a,
        log_path=str(log_file),
        timestamp="2026-11-20T12:00:00Z",
    )

    event_b = log_audit_trail_event(
        agent_name="anomaly_agent",
        event_type="tool_call",
        tool_name="find_duplicates",
        args_summary={"window_days": 5},
        result_data=data_b,
        log_path=str(log_file),
        timestamp="2026-11-20T12:00:00Z",
    )

    # Because keys are sorted and canonicalized, hashes must match exactly
    assert event_a["result_sha256"] == event_b["result_sha256"]
    assert len(event_a["result_sha256"]) == 64

    # Verify log file format is valid JSONL
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert parsed["agent_name"] == "anomaly_agent"
        assert parsed["event_type"] == "tool_call"
        assert parsed["tool_name"] == "find_duplicates"
        assert "result_sha256" in parsed


def test_log_audit_trail_never_logs_raw_secrets_or_pii(tmp_path: Path):
    """Verify that logging an event with sensitive keys scrubs secrets and masks bank accounts."""
    log_file = tmp_path / "scrubbed_trail.jsonl"

    log_audit_trail_event(
        agent_name="vendor_agent",
        event_type="tool_call",
        tool_name="vendor_bank_overlap",
        args_summary={"api_key": "AIzaSySecret", "bank_account": "50200000100291"},
        result_data={"secret_token": "token123", "account": "91201004567801"},
        log_path=str(log_file),
    )

    content = log_file.read_text(encoding="utf-8")
    # Neither raw secret nor raw account number must appear in the log file
    assert "AIzaSySecret" not in content
    assert "50200000100291" not in content
    assert "token123" not in content
    assert "91201004567801" not in content

    # The logged args summary must have secrets and PII redacted
    assert "[REDACTED_SECRET]" in content
    assert "[REDACTED_ACCOUNT_****0291]" in content

    # Result data is cryptographically hashed into result_sha256, not logged in plaintext
    assert "result_sha256" in content


# =====================================================================
# 4. ADK Callback Invocation Tests
# =====================================================================

def test_before_model_guardrail_masks_request_contents(tmp_path: Path, monkeypatch):
    """Verify before_model_guardrail mutates LlmRequest parts in-place to redact bank accounts."""
    log_file = tmp_path / "model_audit_trail.jsonl"
    monkeypatch.setenv("AUDIT_TRAIL_LOG_PATH", str(log_file))

    raw_text = "Vendor 50200000100291 matches employee 91201004567801"
    request = LlmRequest(
        model="gemini-3.5-flash",
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=raw_text)])],
    )

    ctx = MagicMock(spec=CallbackContext)
    ctx.agent_name = "vendor_agent"

    res = before_model_guardrail(callback_context=ctx, llm_request=request)

    # Returns None so normal model execution is permitted
    assert res is None

    # Text in request parts must be masked
    masked_text = request.contents[0].parts[0].text
    assert "50200000100291" not in masked_text
    assert "91201004567801" not in masked_text
    assert "[REDACTED_ACCOUNT_****0291]" in masked_text
    assert "[REDACTED_ACCOUNT_****7801]" in masked_text

    # Audit trail event must be recorded
    assert log_file.is_file()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_type"] == "model_call"
    assert event["agent_name"] == "vendor_agent"


def test_after_tool_audit_logger_records_provenance(tmp_path: Path, monkeypatch):
    """Verify after_tool_audit_logger records tool call and returns None to preserve result."""
    log_file = tmp_path / "tool_audit_trail.jsonl"
    monkeypatch.setenv("AUDIT_TRAIL_LOG_PATH", str(log_file))

    tool = MagicMock(spec=BaseTool)
    tool.name = "find_duplicates"
    tool_args = {"ledger_path": "data/ledger.csv", "window_days": 5}
    tool_resp = {"test": "find_duplicates", "flagged_ids": ["JE-2025-0010"], "exposure": 50000.0}

    tool_ctx = MagicMock(spec=ToolContext)
    tool_ctx.agent_name = "anomaly_agent"

    res = after_tool_audit_logger(
        tool=tool,
        tool_args=tool_args,
        tool_context=tool_ctx,
        result=tool_resp,
    )

    # Preserves tool result unmodified
    assert res is None

    # Audit trail event recorded
    assert log_file.is_file()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event_type"] == "tool_call"
    assert event["tool_name"] == "find_duplicates"
    assert event["agent_name"] == "anomaly_agent"
    assert len(event["result_sha256"]) == 64


def test_pipeline_guard_halts_failed_intake():
    """Verify pipeline_guard returns diagnostic Content when intake failed and None when passed."""
    ctx_fail = MagicMock(spec=CallbackContext)
    ctx_fail.state = {
        "data_profile": {
            "status": "FAILED",
            "failure_reasons": ["Trial balance file missing"],
            "notes": "Validation aborted",
        }
    }

    res_fail = pipeline_guard(ctx_fail)
    assert res_fail is not None
    assert "AUDIT PIPELINE HALTED" in res_fail.parts[0].text
    assert "Trial balance file missing" in res_fail.parts[0].text

    ctx_ok = MagicMock(spec=CallbackContext)
    ctx_ok.state = {"data_profile": {"status": "PASSED_WITH_VARIANCE"}}
    assert pipeline_guard(ctx_ok) is None


# =====================================================================
# 5. Agent Guardrails Registration & Security Isolation Tests
# =====================================================================

def test_all_llm_agents_have_guardrails_attached():
    """Verify that all five LLM agents have before_model_guardrail and after_tool_audit_logger attached."""
    from auditpilot.agents.anomaly import anomaly_agent
    from auditpilot.agents.vendor import vendor_agent
    from auditpilot.agents.ratio import ratio_agent
    from auditpilot.agents.policy import policy_agent
    from auditpilot.agents.skeptic import skeptic_agent

    agents = [
        anomaly_agent,
        vendor_agent,
        ratio_agent,
        policy_agent,
        skeptic_agent,
    ]

    for agent in agents:
        bm = agent.before_model_callback or []
        if not isinstance(bm, list):
            bm = [bm]
        at = agent.after_tool_callback or []
        if not isinstance(at, list):
            at = [at]

        assert before_model_guardrail in bm, f"{agent.name} missing before_model_guardrail"
        assert after_tool_audit_logger in at, f"{agent.name} missing after_tool_audit_logger"


def test_adversarial_prompt_injection_in_ledger_descriptions():
    """Verify that the 4 planted prompt injections in data/ledger.csv are treated strictly as untrusted data."""
    import pandas as pd
    from auditpilot.tools.data_tools import load_ledger
    from auditpilot.tools.anomaly_tools import find_duplicates, find_weekend_round

    ledger_df = pd.read_csv("data/ledger.csv")

    # The 4 planted prompt-injection entry IDs
    injection_ids = ["JE-2025-0741", "JE-2025-2329", "JE-2025-3735", "JE-2025-5221"]

    # Verify all 4 exist in the dataset
    found = ledger_df[ledger_df["entry_id"].isin(injection_ids)]
    assert len(found) == 4

    # Verify descriptions contain injection payloads
    descriptions = found["description"].str.upper().tolist()
    assert any("SYSTEM OVERRIDE" in d for d in descriptions)
    assert any("ADMIN COMMAND" in d for d in descriptions)
    assert any("AI AGENT INSTRUCTION" in d for d in descriptions)
    assert any("SECURITY OVERRIDE" in d for d in descriptions)

    # Deterministic tools evaluate only structured columns and double-entry math
    load_res = load_ledger("data/ledger.csv")
    assert load_res["stats"]["is_valid"] is True
    assert load_res["stats"]["is_balanced"] is True

    # Prompt injections do not prevent anomaly detection
    dup_res = find_duplicates("data/ledger.csv")
    assert len(dup_res["flagged_ids"]) > 0

    wknd_res = find_weekend_round("data/ledger.csv")
    assert len(wknd_res["flagged_ids"]) == 12


def test_ground_truth_isolation_from_production_code():
    """Verify ground_truth.csv is never accessed or referenced by production audit code in auditpilot/."""
    import subprocess
    res = subprocess.run(
        ["grep", "-rn", "ground_truth", "auditpilot/"],
        capture_output=True,
        text=True,
    )

    # Return code 1 means no matches were found in auditpilot/ (safe isolation)
    assert res.returncode == 1, (
        f"Production code in auditpilot/ illegally references ground_truth: {res.stdout}"
    )
