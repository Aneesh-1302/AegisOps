"""
AegisOps — Tool: Data Batch Isolation (GCS)

Quarantines a problematic data batch by moving it to an isolated
GCS location and tagging it with metadata.

DUAL MODE:
  • If google-cloud-storage is configured → real GCS API calls
  • Otherwise → mock/stub that logs the action

Website spec: "Agent calls GCS tool to tag or quarantine the flagged
data batch. Prevents it from contaminating future training runs."
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .retry import with_retry


# ---------------------------------------------------------------------------
# Input Schema
# ---------------------------------------------------------------------------

class DataIsolationInput(BaseModel):
    """Input schema for the data isolation tool."""

    batch_id: str = Field(
        ...,
        description=(
            "Unique identifier of the data batch to isolate. "
            "e.g. 'batch-20260606-us-west2-0437'."
        ),
    )
    model_name: str = Field(
        ...,
        description="The affected model's fully-qualified resource name.",
    )
    reason: str = Field(
        ...,
        description="Why this batch is being isolated (for audit logging).",
    )
    source_bucket: str = Field(
        default="",
        description=(
            "GCS bucket containing the batch. If empty, uses the "
            "GCS_DATA_BUCKET environment variable."
        ),
    )
    quarantine_destination: str = Field(
        default="",
        description=(
            "GCS path for quarantine. If empty, uses "
            "gs://{bucket}/quarantine/{batch_id}/."
        ),
    )


# ---------------------------------------------------------------------------
# GCS Availability Check
# ---------------------------------------------------------------------------

def _gcs_available() -> bool:
    """Check if google-cloud-storage is installed and credentials exist."""
    try:
        from google.cloud import storage  # noqa: F401
        # Check for credentials
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return True
        # Try default credentials
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
def isolate_data_batch(
    batch_id: str,
    model_name: str,
    reason: str,
    source_bucket: str = "",
    quarantine_destination: str = "",
) -> dict:
    """
    Quarantine a data batch by moving it to an isolated GCS location.

    If GCS credentials are configured, this performs real Cloud Storage
    operations. Otherwise, it runs in mock mode for demo purposes.

    The agent calls this tool when it detects data drift (moderate severity)
    to prevent contaminated data from affecting future training runs.

    Args:
        batch_id: Unique batch identifier to isolate.
        model_name: Affected model's full resource name.
        reason: Explanation of why isolation is needed.
        source_bucket: GCS bucket name (or uses GCS_DATA_BUCKET env var).
        quarantine_destination: GCS quarantine path.

    Returns:
        dict with isolation confirmation, including the quarantine path.
    """
    # Validate inputs
    validated = DataIsolationInput(
        batch_id=batch_id,
        model_name=model_name,
        reason=reason,
        source_bucket=source_bucket,
        quarantine_destination=quarantine_destination,
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    bucket_name = validated.source_bucket or os.environ.get(
        "GCS_DATA_BUCKET", "ops-agent-data"
    )
    quarantine_path = validated.quarantine_destination or (
        f"gs://{bucket_name}/quarantine/{validated.batch_id}/"
    )

    # ── Real GCS mode ─────────────────────────────────────────────────
    if _gcs_available():
        from google.cloud import storage

        client = storage.Client()
        bucket = client.bucket(bucket_name)

        # Move objects with the batch prefix to quarantine
        source_prefix = f"data/{validated.batch_id}/"
        quarantine_prefix = f"quarantine/{validated.batch_id}/"

        moved_count = 0
        blobs = list(bucket.list_blobs(prefix=source_prefix))

        for blob in blobs:
            new_name = blob.name.replace(source_prefix, quarantine_prefix)
            bucket.rename_blob(blob, new_name)
            moved_count += 1

        # Tag the quarantine directory with metadata
        marker = bucket.blob(f"{quarantine_prefix}_QUARANTINE_METADATA.json")
        import json
        marker.upload_from_string(
            json.dumps({
                "batch_id": validated.batch_id,
                "model_name": validated.model_name,
                "reason": validated.reason,
                "quarantined_at": timestamp,
                "objects_moved": moved_count,
            }),
            content_type="application/json",
        )

        print(f"\n  [GCS] Batch '{validated.batch_id}' quarantined.")
        print(f"     Moved {moved_count} objects to {quarantine_path}")
        print(f"     Reason: {validated.reason}\n")

        return {
            "success": True,
            "mode": "gcs_live",
            "batch_id": validated.batch_id,
            "model_name": validated.model_name,
            "quarantine_destination": quarantine_path,
            "objects_moved": moved_count,
            "quarantined_at": timestamp,
            "message": (
                f"Batch '{validated.batch_id}' isolated to {quarantine_path}. "
                f"{moved_count} objects moved."
            ),
        }

    # ── Mock/stub mode ────────────────────────────────────────────────
    print(f"\n  [MOCK] Batch '{validated.batch_id}' would be quarantined.")
    print(f"     Destination: {quarantine_path}")
    print(f"     Reason: {validated.reason}\n")

    return {
        "success": True,
        "mode": "mock",
        "batch_id": validated.batch_id,
        "model_name": validated.model_name,
        "quarantine_destination": quarantine_path,
        "objects_moved": 0,
        "quarantined_at": timestamp,
        "message": (
            f"[MOCK] Batch '{validated.batch_id}' isolated to {quarantine_path}. "
            f"(No GCS credentials — running in demo mode.)"
        ),
    }
