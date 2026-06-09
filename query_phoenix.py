from phoenix.client import Client
from datetime import datetime, timedelta
import json

client = Client(base_url="http://localhost:6006")

spans_df = client.spans.get_spans_dataframe(
    project_identifier="unified-ai-ops",
    limit=500,
    start_time=datetime.now() - timedelta(days=7)
)

# Extract nested fields
spans_df["batch"] = spans_df["attributes.model"].apply(lambda x: x.get("batch") if isinstance(x, dict) else None)
spans_df["confidence"] = spans_df["attributes.output"].apply(lambda x: x.get("confidence") if isinstance(x, dict) else None)
spans_df["severity"] = spans_df["attributes.drift"].apply(lambda x: x.get("severity") if isinstance(x, dict) else None)

def compute_drift_event(batch_num):
    batch_spans = spans_df[spans_df["batch"] == batch_num]

    if batch_spans.empty:
        print(f"No spans for batch {batch_num}")
        return None

    avg_latency = batch_spans["attributes.latency_ms"].mean()
    avg_confidence = batch_spans["confidence"].mean()
    severity = batch_spans["severity"].iloc[0]

    # Match P1's exact contract
    drift_event = {
        "drift_event": {
            "model_id": "projects/unified-ai-ops/locations/us-central1/models/fraud-classifier-v2",
            "metric": "latency_p99",
            "severity": severity,
            "batch_window": f"batch_{batch_num}",
            "baseline_value": 40.0,
            "observed_value": round(avg_latency, 2),
            "batch_id": f"batch-{batch_num}",
            "endpoint_id": "fraud-classifier-serving",
            "previous_good_version": "fraud-classifier-serving-v1-00001",
        },
        "context": {
            "performance": {
                "confidence_observed": round(avg_confidence, 3),
                "confidence_baseline": 0.92,
                "latency_p50_ms": round(avg_latency * 0.8, 2),
                "latency_p99_ms": round(avg_latency, 2),
            },
            "status": f"Drift detected at batch {batch_num} — severity: {severity}"
        }
    }

    return drift_event

for batch in [2, 3, 4, 5]:
    event = compute_drift_event(batch)
    print(f"\nBatch {batch}:")
    print(json.dumps(event, indent=2))