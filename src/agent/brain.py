"""
AegisOps — Brain (ADK v2.2 · Website-Aligned)

The central ADK Agent, fully aligned with the AegisOps website spec:

  • Model:  gemini-2.0-flash (per website Tech Stack)
  • Tools:  4 tools (isolate, retrain, rollback, incident_report)
  • MCP:    Arize Phoenix via McpToolset
  • Demo:   3 scenarios using drift_event JSON contract format

Provides two execution paths:
  1. `root_agent`          — For `adk web .` and `adk run .`
  2. `evaluate_telemetry()` — Programmatic entry point
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from typing import Any

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from mcp import StdioServerParameters
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams

# ── Load environment variables early ──────────────────────────────────────
load_dotenv()

# ── Import the system prompt ─────────────────────────────────────────────
from .prompts import AI_OPS_SYSTEM_PROMPT

# ── Import our 4 custom action tools (raw functions) ─────────────────────
# ADK inspects type hints + docstrings to auto-generate FunctionDeclarations.
from ..tools.pipeline_trigger import trigger_retraining_pipeline
from ..tools.data_isolator import isolate_data_batch
from ..tools.rollback_executor import rollback_deployment
from ..tools.incident_reporter import generate_incident_report


# ---------------------------------------------------------------------------
# MCP Toolset — Arize Phoenix Integration (P2's domain)
# ---------------------------------------------------------------------------

def _build_arize_mcp_toolset():
    """
    Build an ADK McpToolset for the Arize Phoenix MCP server (stdio).

    This is the integration point with Person 2. P2 runs the Arize MCP
    server that exposes drift_event data; P1's agent consumes it.

    Returns None if npx or MCP config is unavailable.
    """
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        npx_path = shutil.which("npx")
        if not npx_path:
            print("    npx not found — Arize MCP tools disabled")
            return None

        arize_api_key = os.environ.get("ARIZE_API_KEY", "")
        arize_base_url = os.environ.get(
            "ARIZE_BASE_URL", "https://app.phoenix.arize.com"
        )

        server_params = StdioServerParameters(
            command=npx_path,
            args=[
                "-y", "@arizeai/phoenix-mcp@latest",
                "--baseUrl", arize_base_url,
                "--apiKey", arize_api_key,
            ],
            env={**os.environ},
        )

        toolset = McpToolset(
            connection_params=StdioConnectionParams(server_params=server_params),
        )
        print("    Arize MCP toolset configured (stdio via npx)")
        return toolset

    except Exception as e:
        print(f"    Arize MCP toolset setup failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Agent Construction
# ---------------------------------------------------------------------------

# The 4 custom tools — passed as raw callables
CUSTOM_TOOLS: list[Any] = [
    isolate_data_batch,
    trigger_retraining_pipeline,
    rollback_deployment,
    generate_incident_report,
]


def build_agent(include_mcp: bool = True) -> Agent:
    """
    Construct the fully configured ADK Agent.

    Args:
        include_mcp: Whether to connect the Arize MCP toolset.

    Returns:
        A google.adk.agents.Agent wired with all tools and the
        AegisOps system instruction.
    """
    tools: list[Any] = list(CUSTOM_TOOLS)

    if include_mcp:
        mcp_toolset = _build_arize_mcp_toolset()
        if mcp_toolset is not None:
            tools.append(mcp_toolset)

    agent = Agent(
        name="aegisops_agent",
        model="gemini-2.5-flash",       # Gemini 2.5 Flash (fast + capable)
        instruction=AI_OPS_SYSTEM_PROMPT,
        tools=tools,
    )

    return agent


# ---------------------------------------------------------------------------
# Root agent instance — used by `adk web .` and `adk run .`
# ---------------------------------------------------------------------------

root_agent = build_agent(include_mcp=True)


# ---------------------------------------------------------------------------
# Programmatic Entry Point: evaluate_telemetry
# ---------------------------------------------------------------------------

async def evaluate_telemetry(
    telemetry_context: str,
    agent: Agent | None = None,
) -> str:
    """
    Programmatic entry point — sends telemetry to the agent and
    streams its response events to the console.

    Args:
        telemetry_context: Raw telemetry data (JSON or text) to analyze.
        agent: Optional pre-built Agent. Uses root_agent if None.

    Returns:
        str: The agent's final text response.
    """
    if agent is None:
        agent = root_agent

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="aegisops_agent",
        session_service=session_service,
    )

    user_id = "ops-engineer"
    session = await session_service.create_session(
        app_name="aegisops_agent",
        user_id=user_id,
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            "A drift event has been detected by the Arize Phoenix monitoring "
            "system. Analyze the following telemetry, classify the severity, "
            "and execute the appropriate remediation actions per your decision "
            "matrix.\n\n"
            "--- BEGIN TELEMETRY ---\n"
            f"{telemetry_context}\n"
            "--- END TELEMETRY ---"
        ))],
    )

    print(f"\n{'━' * 60}")
    print(f"    TELEMETRY SUBMITTED — Session: {session.id}")
    print(f"{'━' * 60}\n")

    final_response = ""

    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"  [{event.author}]: {part.text}\n")
                    final_response = part.text

                if part.function_call:
                    print(f"  [{event.author}] TOOL CALL: {part.function_call.name}")
                    if part.function_call.args:
                        print(f"     Args: {json.dumps(dict(part.function_call.args), indent=2)}")
                    print()

                if part.function_response:
                    print(f"  [{event.author}] TOOL RESULT: {part.function_response.name}")
                    print()

    print(f"{'━' * 60}")
    print(f"    Evaluation complete.")
    print(f"{'━' * 60}\n")

    return final_response


# ---------------------------------------------------------------------------
# Interactive Demo Mode
# ---------------------------------------------------------------------------

async def run_agent_loop(
    agent: Agent | None = None,
    **kwargs,
) -> None:
    """
    Interactive CLI demo — presents 3 scenarios from the website spec.
    For the web UI, use `adk web .` instead.
    """
    if agent is None:
        agent = root_agent

    print(f"\n{'━' * 60}")
    print(f"    AEGISOPS — AegisOps")
    print(f"{'━' * 60}")
    print("  Autonomous MLOps remediation powered by Google ADK.\n")

    scenarios = {
        "1": {
            "name": "Moderate — Data Drift (isolate + retrain)",
            "telemetry": DEMO_DRIFT_MODERATE,
        },
        "2": {
            "name": "Critical — Production Degradation (rollback)",
            "telemetry": DEMO_DEGRADATION_CRITICAL,
        },
        "3": {
            "name": "Low — Stable Operations (passive monitor)",
            "telemetry": DEMO_STABLE_LOW,
        },
    }

    print("  Scenarios:")
    for key, scenario in scenarios.items():
        print(f"   [{key}] {scenario['name']}")
    print(f"   [q] Quit\n")

    while True:
        try:
            choice = input("  Select scenario (1/2/3/q): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\n   Agent shutting down.\n")
            break

        if choice == "q":
            print("\n   Agent shutting down.\n")
            break

        if choice not in scenarios:
            print("    Invalid choice. Try 1, 2, 3, or q.\n")
            continue

        scenario = scenarios[choice]
        print(f"\n{'═' * 60}")
        print(f"   SCENARIO: {scenario['name']}")
        print(f"{'═' * 60}")

        await evaluate_telemetry(
            telemetry_context=scenario["telemetry"],
            agent=agent,
        )

        print(f"\n{'═' * 60}")
        print("  Scenario complete. Select another or press 'q' to quit.")
        print(f"{'═' * 60}\n")


# ---------------------------------------------------------------------------
# Demo Telemetry — drift_event contract format per website spec
# ---------------------------------------------------------------------------
# These match the JSON contract agreed between P1 and P2:
#   drift_event.model_id, .metric, .severity, .batch_window,
#   .baseline_value, .observed_value

DEMO_DRIFT_MODERATE = json.dumps({
    "drift_event": {
        "model_id": "projects/acme-prod/locations/us-central1/models/fraud-detector-v3",
        "metric": "psi",
        "severity": "moderate",
        "batch_window": "2026-06-06T00:00:00Z/2026-06-06T06:00:00Z",
        "baseline_value": 0.05,
        "observed_value": 0.38,
        "batch_id": "batch-20260606-us-west2-0437",
        "endpoint_id": "fraud-detector-serving",
        "previous_good_version": "fraud-detector-serving-v2-00001",
    },
    "context": {
        "features_affected": ["income_bracket", "geo_region"],
        "psi_scores": {
            "transaction_amount": 0.08,
            "merchant_category": 0.05,
            "customer_age": 0.12,
            "income_bracket": 0.38,
            "geo_region": 0.42,
            "device_type": 0.06,
        },
        "performance": {
            "accuracy_24h": 0.91,
            "accuracy_baseline": 0.94,
            "f1_24h": 0.88,
            "f1_baseline": 0.92,
            "latency_p50_ms": 45,
            "latency_p99_ms": 120,
            "error_rate_5xx": 0.003,
        },
        "root_cause": (
            "Upstream data pipeline changed encoding for income_bracket "
            "and geo_region fields starting with batch-20260606-us-west2-0437. "
            "New encoding maps different categorical values."
        ),
        "dataset_uri": "gs://acme-prod-data/fraud-detector/training/cleaned_v20260607",
    },
}, indent=2)


DEMO_DEGRADATION_CRITICAL = json.dumps({
    "drift_event": {
        "model_id": "projects/acme-prod/locations/us-central1/models/fraud-detector-v3",
        "metric": "accuracy_delta",
        "severity": "critical",
        "batch_window": "2026-06-07T06:00:00Z/2026-06-07T06:25:00Z",
        "baseline_value": 0.94,
        "observed_value": 0.61,
        "batch_id": None,
        "endpoint_id": "fraud-detector-serving",
        "previous_good_version": "fraud-detector-serving-v2-00001",
    },
    "context": {
        "performance": {
            "accuracy_1h": 0.61,
            "accuracy_baseline": 0.94,
            "f1_1h": 0.55,
            "f1_baseline": 0.92,
            "latency_p50_ms": 380,
            "latency_p99_ms": 2400,
            "error_rate_5xx": 0.124,
        },
        "incident_timeline": [
            "06:00 - Normal operations",
            "06:12 - Latency p50 jumps from 42ms to 180ms",
            "06:15 - 5xx error rate crosses 5% threshold",
            "06:18 - Accuracy drops below 0.70",
            "06:22 - Latency p99 exceeds 2000ms",
            "06:25 - System in degraded state",
        ],
        "hypothesis": (
            "No data drift detected. Likely cause: model artifact corruption "
            "during latest deployment (v3 deployed at 06:10). Previous version "
            "(v2) was stable for 3 weeks."
        ),
        "revenue_impact_per_hour": 12000,
    },
}, indent=2)


DEMO_STABLE_LOW = json.dumps({
    "drift_event": {
        "model_id": "projects/acme-prod/locations/us-central1/models/fraud-detector-v3",
        "metric": "psi",
        "severity": "low",
        "batch_window": "2026-06-07T00:00:00Z/2026-06-07T06:00:00Z",
        "baseline_value": 0.05,
        "observed_value": 0.03,
        "batch_id": None,
        "endpoint_id": "fraud-detector-serving",
        "previous_good_version": "fraud-detector-serving-v2-00001",
    },
    "context": {
        "performance": {
            "accuracy_24h": 0.943,
            "accuracy_baseline": 0.94,
            "f1_24h": 0.921,
            "f1_baseline": 0.92,
            "latency_p50_ms": 41,
            "latency_p99_ms": 112,
            "error_rate_5xx": 0.0015,
        },
        "psi_scores": {
            "transaction_amount": 0.03,
            "merchant_category": 0.02,
            "customer_age": 0.04,
            "income_bracket": 0.01,
            "geo_region": 0.02,
            "device_type": 0.01,
        },
        "status": "All systems operating normally. No anomalies detected.",
    },
}, indent=2)
