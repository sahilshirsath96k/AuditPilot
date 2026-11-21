"""Production FastAPI entry point for AuditPilot."""

from pathlib import Path

from fastapi import FastAPI
from google.adk.cli.fast_api import AgentLoader, get_fast_api_app

PROJECT_ROOT = Path(__file__).resolve().parent
AGENT_DIR = PROJECT_ROOT / "auditpilot"

agent_loader = AgentLoader(agents_dir=str(AGENT_DIR))

app: FastAPI = get_fast_api_app(
    agents_dir=str(AGENT_DIR),
    agent_loader=agent_loader,
    web=True,
    port=8080,
    reload_agents=False,
)
