"""
AegisOps — Tool: Retraining Pipeline Trigger (Vertex AI)

Triggers a Vertex AI Training Pipeline to retrain a model when the
agent detects significant drift.

DUAL MODE:
  • If google-cloud-aiplatform is configured → real Vertex AI API calls
  • Otherwise → mock that simulates pipeline submission

Website spec: "Agent submits Vertex AI Pipeline run with clean data
window. Passes training config, dataset version, and experiment tag."
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from .retry import with_retry


# ---------------------------------------------------------------------------
# Input Schema
# ---------------------------------------------------------------------------

class RetrainingUrgency(str, Enum):
    """How urgently the retraining should be scheduled."""
    LOW = "low"
    NORMAL = "normal"
    CRITICAL = "critical"


class RetrainingPipelineInput(BaseModel):
    """Strict input schema for the retraining pipeline trigger."""

    model_name: str = Field(
        ...,
        description=(
            "Fully-qualified name of the model to retrain, e.g. "
            "'projects/my-proj/locations/us-central1/models/fraud-detector'."
        ),
    )
    dataset_uri: str = Field(
        ...,
        description=(
            "GCS URI of the training dataset to use, e.g. "
            "'gs://my-bucket/datasets/fraud-v3/'. If a problematic batch "
            "was isolated, this should point to the cleaned dataset."
        ),
    )
    pipeline_template_uri: Optional[str] = Field(
        default=None,
        description=(
            "GCS URI of the pipeline template JSON/YAML. "
            "Defaults to the VERTEX_PIPELINE_TEMPLATE env var if omitted."
        ),
    )
    urgency: RetrainingUrgency = Field(
        default=RetrainingUrgency.NORMAL,
        description="Scheduling priority for the retraining job.",
    )
    reason: str = Field(
        ...,
        description=(
            "Human-readable explanation of why retraining was triggered. "
            "This is logged for audit purposes."
        ),
    )
    notify_on_completion: bool = Field(
        default=True,
        description="Whether to send a notification when the pipeline finishes.",
    )


# ---------------------------------------------------------------------------
# Vertex AI Availability Check
# ---------------------------------------------------------------------------

def _vertex_available() -> bool:
    """Check if google-cloud-aiplatform is installed and credentials exist."""
    try:
        from google.cloud import aiplatform  # noqa: F401
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return True
        try:
            import google.auth
            google.auth.default()
            return True
        except Exception:
            return False
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Tool Implementation
# ---------------------------------------------------------------------------

@with_retry(max_attempts=3)
def trigger_retraining_pipeline(
    model_name: str,
    dataset_uri: str,
    pipeline_template_uri: str | None = None,
    urgency: str = "normal",
    reason: str = "Agent-triggered retraining",
    notify_on_completion: bool = True,
) -> dict:
    """
    Trigger a Vertex AI retraining pipeline for the specified model.

    If Vertex AI credentials are configured, this submits a real
    PipelineJob. Otherwise, it runs in mock mode for demo purposes.

    The agent calls this after isolating a bad data batch (moderate
    severity) to retrain the model on cleaned data.

    Args:
        model_name: Fully-qualified model resource name.
        dataset_uri: GCS URI of the training dataset.
        pipeline_template_uri: GCS path to the pipeline template.
        urgency: One of "low", "normal", "critical".
        reason: Audit log reason for the retraining.
        notify_on_completion: Send notification when done.

    Returns:
        dict: Pipeline run details including run ID and status.
    """
    # Validate inputs
    validated = RetrainingPipelineInput(
        model_name=model_name,
        dataset_uri=dataset_uri,
        pipeline_template_uri=pipeline_template_uri,
        urgency=RetrainingUrgency(urgency),
        reason=reason,
        notify_on_completion=notify_on_completion,
    )

    template = validated.pipeline_template_uri or os.environ.get(
        "VERTEX_PIPELINE_TEMPLATE",
        "gs://default-bucket/pipeline-templates/retrain.json",
    )
    pipeline_root = os.environ.get(
        "VERTEX_PIPELINE_ROOT",
        "gs://default-bucket/pipeline-runs",
    )
    run_id = f"retrain-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()

    # Duration estimate scales with urgency
    duration_map = {"low": 120, "normal": 60, "critical": 30}
    est_duration = duration_map.get(validated.urgency.value, 60)

    # ── Real Vertex AI mode ───────────────────────────────────────────
    if _vertex_available():
        from google.cloud import aiplatform

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

        aiplatform.init(project=project, location=location)

        job = aiplatform.PipelineJob(
            display_name=run_id,
            template_path=template,
            pipeline_root=pipeline_root,
            parameter_values={
                "model_name": validated.model_name,
                "dataset_uri": validated.dataset_uri,
                "reason": validated.reason,
            },
        )
        job.submit()

        print(f"\n{'─' * 60}")
        print(f"   PIPELINE TRIGGER [VERTEX AI] — {run_id}")
        print(f"{'─' * 60}")
        print(f"  Model:    {validated.model_name}")
        print(f"  Dataset:  {validated.dataset_uri}")
        print(f"  Template: {template}")
        print(f"  Urgency:  {validated.urgency.value}")
        print(f"  Reason:   {validated.reason}")
        print(f"  Job Name: {job.resource_name}")
        print(f"{'─' * 60}\n")

        return {
            "success": True,
            "mode": "vertex_ai_live",
            "pipeline_run_id": run_id,
            "pipeline_job_name": job.resource_name,
            "model_name": validated.model_name,
            "dataset_uri": validated.dataset_uri,
            "urgency": validated.urgency.value,
            "triggered_at": now,
            "message": (
                f"Retraining pipeline '{run_id}' submitted to Vertex AI. "
                f"Job: {job.resource_name}"
            ),
        }

    # ── Mock mode ─────────────────────────────────────────────────────
    print(f"\n{'─' * 60}")
    print(f"   PIPELINE TRIGGER [MOCK] — {run_id}")
    print(f"{'─' * 60}")
    print(f"  Model:    {validated.model_name}")
    print(f"  Dataset:  {validated.dataset_uri}")
    print(f"  Template: {template}")
    print(f"  Urgency:  {validated.urgency.value}")
    print(f"  Reason:   {validated.reason}")
    print(f"  ETA:      ~{est_duration} minutes")
    print(f"{'─' * 60}\n")

    return {
        "success": True,
        "mode": "mock",
        "pipeline_run_id": run_id,
        "pipeline_run_uri": f"{pipeline_root}/{run_id}",
        "model_name": validated.model_name,
        "dataset_uri": validated.dataset_uri,
        "urgency": validated.urgency.value,
        "estimated_duration_minutes": est_duration,
        "triggered_at": now,
        "message": (
            f"[MOCK] Retraining pipeline '{run_id}' submitted. "
            f"Model: {validated.model_name} | Dataset: {validated.dataset_uri} | "
            f"ETA: ~{est_duration} min"
        ),
    }
