"""
AegisOps — Tool: Deployment Rollback (Cloud Run)

Rolls back the currently-deployed model serving endpoint on Cloud Run
to the last known-good revision when critical degradation is detected.

DUAL MODE:
  • If google-cloud-run is configured → real Cloud Run Admin API calls
  • Otherwise → mock that simulates the rollback

Website spec: "Agent calls Cloud Run API to swap active revision to
last known-good version. Zero downtime. Confirms new revision is healthy."
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .retry import with_retry


# ---------------------------------------------------------------------------
# Input Schema
# ---------------------------------------------------------------------------

class RollbackInput(BaseModel):
    """Input schema for the Cloud Run rollback tool."""

    service_name: str = Field(
        ...,
        description=(
            "Cloud Run service name to rollback, e.g. 'fraud-detector-serving'. "
            "Can also be a fully-qualified resource name."
        ),
    )
    target_revision: str = Field(
        ...,
        description=(
            "The Cloud Run revision to rollback TO (last known-good). "
            "e.g. 'fraud-detector-serving-v2-00001' or a version tag."
        ),
    )
    reason: str = Field(
        ...,
        description="Explanation of why the rollback is being performed.",
    )
    traffic_percent: int = Field(
        default=100,
        description=(
            "Percentage of traffic to send to the target revision. "
            "Default 100 for full rollback. Use lower for canary."
        ),
    )


# ---------------------------------------------------------------------------
# Cloud Run Availability Check
# ---------------------------------------------------------------------------

def _cloud_run_available() -> bool:
    """Check if google-cloud-run is installed and credentials exist."""
    try:
        from google.cloud import run_v2  # noqa: F401
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
def rollback_deployment(
    service_name: str,
    target_revision: str,
    reason: str,
    traffic_percent: int = 100,
) -> dict:
    """
    Rollback a Cloud Run service to a previous stable revision.

    If Cloud Run credentials are configured, this performs a real
    traffic migration. Otherwise, it runs in mock mode for demo.

    The agent calls this immediately when it detects critical severity
    degradation — protecting production before investigating root cause.

    Args:
        service_name: Cloud Run service name to rollback.
        target_revision: The revision to rollback TO (last known-good).
        reason: Why the rollback is happening.
        traffic_percent: Traffic percentage for the target revision.

    Returns:
        dict with rollback confirmation details.
    """
    validated = RollbackInput(
        service_name=service_name,
        target_revision=target_revision,
        reason=reason,
        traffic_percent=traffic_percent,
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "demo-project")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    # ── Real Cloud Run mode ───────────────────────────────────────────
    if _cloud_run_available():
        from google.cloud.run_v2 import ServicesClient
        from google.cloud.run_v2.types import (
            Service,
            TrafficTarget,
            TrafficTargetAllocationType,
            UpdateServiceRequest,
        )

        client = ServicesClient()
        service_path = (
            f"projects/{project}/locations/{location}"
            f"/services/{validated.service_name}"
        )

        # Get current service
        service = client.get_service(name=service_path)

        # Update traffic to point to target revision
        service.traffic = [
            TrafficTarget(
                type_=TrafficTargetAllocationType.TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION,
                revision=validated.target_revision,
                percent=validated.traffic_percent,
            ),
        ]

        update_request = UpdateServiceRequest(service=service)
        operation = client.update_service(request=update_request)
        result = operation.result()

        print(f"\n  [CLOUD RUN] Rollback on '{validated.service_name}'")
        print(f"     Target revision: {validated.target_revision}")
        print(f"     Traffic: {validated.traffic_percent}%")
        print(f"     Reason: {validated.reason}")
        print(f"     Status: COMPLETED\n")

        return {
            "success": True,
            "mode": "cloud_run_live",
            "service_name": validated.service_name,
            "target_revision": validated.target_revision,
            "traffic_percent": validated.traffic_percent,
            "rolled_back_at": timestamp,
            "service_uri": result.uri if hasattr(result, 'uri') else service_path,
            "message": (
                f"Cloud Run service '{validated.service_name}' rolled back to "
                f"'{validated.target_revision}' ({validated.traffic_percent}% traffic)."
            ),
        }

    # ── Mock mode ─────────────────────────────────────────────────────
    print(f"\n  [MOCK] Rollback on '{validated.service_name}'")
    print(f"     Target revision: {validated.target_revision}")
    print(f"     Traffic: {validated.traffic_percent}%")
    print(f"     Reason: {validated.reason}")
    print(f"     Status: COMPLETED (mock)\n")

    return {
        "success": True,
        "mode": "mock",
        "service_name": validated.service_name,
        "target_revision": validated.target_revision,
        "traffic_percent": validated.traffic_percent,
        "rolled_back_at": timestamp,
        "message": (
            f"[MOCK] Cloud Run service '{validated.service_name}' rolled back to "
            f"'{validated.target_revision}' ({validated.traffic_percent}% traffic). "
            f"(No Cloud Run credentials — running in demo mode.)"
        ),
    }
