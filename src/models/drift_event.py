"""
AegisOps — Drift Event Contract

This is the **integration contract between Person 1 (Agent) and Person 2 (Telemetry)**.

Person 2's Arize MCP server emits drift events matching this schema.
Person 1's ADK agent consumes them and decides on remediation actions.

The severity enum directly maps to the agent's decision matrix:
  • low      → passive monitoring (alert only, no tool calls)
  • moderate → isolate_data_batch → trigger_retraining_pipeline
  • critical → rollback_deployment immediately
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums — agreed contract between P1 and P2
# ---------------------------------------------------------------------------

class DriftMetric(str, Enum):
    """The type of drift signal detected by Arize."""
    PSI = "psi"
    ACCURACY_DELTA = "accuracy_delta"
    LATENCY_P99 = "latency_p99"


class DriftSeverity(str, Enum):
    """
    Severity classification — determines agent action.

    P2 (Arize/MCP) sets this based on thresholds:
      • PSI > 0.2 but < 0.5    → moderate
      • PSI > 0.5              → critical
      • accuracy drop > 5%     → moderate
      • accuracy drop > 15%    → critical
      • latency_p99 > 2x       → moderate
      • latency_p99 > 5x       → critical
    """
    LOW = "low"
    MODERATE = "moderate"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Core Contract Schema
# ---------------------------------------------------------------------------

class DriftEvent(BaseModel):
    """
    Structured drift event — the JSON contract between P1 and P2.

    P2's MCP server surfaces this to P1's ADK agent.
    The agent uses severity + metric to choose the correct action.
    """

    model_id: str = Field(
        ...,
        description=(
            "Vertex AI model resource name. "
            "e.g. 'projects/acme-prod/locations/us-central1/models/fraud-detector-v3'"
        ),
    )
    metric: DriftMetric = Field(
        ...,
        description="The type of drift signal: psi, accuracy_delta, or latency_p99.",
    )
    severity: DriftSeverity = Field(
        ...,
        description=(
            "How severe the drift is. Directly maps to agent action: "
            "low → alert, moderate → isolate+retrain, critical → rollback."
        ),
    )
    batch_window: str = Field(
        ...,
        description=(
            "ISO 8601 time range for the data slice that drifted. "
            "e.g. '2026-06-06T00:00:00Z/2026-06-06T06:00:00Z'"
        ),
    )
    baseline_value: float = Field(
        ...,
        description="The expected/baseline metric value.",
    )
    observed_value: float = Field(
        ...,
        description="The current/observed metric value.",
    )

    # Optional enrichment fields (P2 may provide)
    batch_id: Optional[str] = Field(
        default=None,
        description="Specific batch ID if identified.",
    )
    endpoint_id: Optional[str] = Field(
        default=None,
        description="Vertex AI / Cloud Run endpoint resource name.",
    )
    previous_good_version: Optional[str] = Field(
        default=None,
        description="Last known-good model version for rollback.",
    )

    def delta_pct(self) -> float:
        """Compute the percentage change from baseline."""
        if self.baseline_value == 0:
            return 0.0
        return ((self.observed_value - self.baseline_value) / self.baseline_value) * 100

    def summary(self) -> str:
        """One-line human-readable summary of the drift event."""
        return (
            f"[{self.severity.value.upper()}] {self.metric.value} drift on "
            f"{self.model_id.split('/')[-1]}: "
            f"baseline={self.baseline_value:.4f} → observed={self.observed_value:.4f} "
            f"(Δ{self.delta_pct():+.1f}%) | batch_window={self.batch_window}"
        )
