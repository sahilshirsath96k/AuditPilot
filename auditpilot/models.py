"""Gemini model factory and configuration for AuditPilot agents."""

import os
from pathlib import Path
from dotenv import load_dotenv
from google.adk.models.google_llm import Gemini
from google.genai.types import HttpRetryOptions

load_dotenv(Path(__file__).resolve().parent / ".env")

def get_gemini_model(model_name: str | None = None) -> Gemini:
    """Configures a Gemini model instance with automatic backoff retry on 503/429 spikes.

    Args:
        model_name: Optional override model identifier. Defaults to GEMINI_MODEL env var
                    or 'gemini-3.5-flash' (baseline from Phase 0).

    Returns:
        Configured Gemini model instance with exponential jitter backoff on transient errors.
    """
    name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    retry_options = HttpRetryOptions(
        attempts=5,
        initial_delay=2.0,
        max_delay=12.0,
        exp_base=2.0,
        jitter=1.0,
        http_status_codes=[408, 429, 500, 502, 503, 504],
    )
    return Gemini(model=name, retry_options=retry_options)
