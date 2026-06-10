import asyncio
import json
from datetime import datetime, timedelta
from phoenix.client import Client

client = Client(base_url="http://localhost:6006")

POLL_INTERVAL_SECONDS = 10
OUTPUT_FILE = "latest_drift_event.json"
alerted_batches = set()

def get_latest_drift_event():
    spans_df = client.spans.get_spans_dataframe(
        project_identifier="unified-ai-ops",
        limit=500,
        start_time=datetime.now() - timedelta(days=7)
    )

    if spans_df is None or spans_df.empty:
        return None

    spans_df["batch"] = spans_df["attributes.model"].apply(lambda x: x.get("batch") if isinstance(x, dict) else None)
    spans_df["confidence"] = spans_df["attributes.output"].apply(lambda x: x.get("confidence") if isinstance(x, dict) else None)
    spans_df["severity"] = spans_df["attributes.drift"].apply(lambda x: x.get("severity") if isinstance(x, dict) else None)

    drifted = spans_df[spans_df["severity"].isin(["low", "moderate", "critical"])]
    if drifted.empty:
        return None

    latest_batch = drifted["batch"].max()
    if latest_batch in alerted_batches:
        return None

    batch_spans = drifted[drifted["batch"] == latest_batch]
    avg_latency = batch_spans["attributes.latency_ms"].mean()
    avg_confidence = batch_spans["confidence"].mean()
    severity = batch_spans["severity"].iloc[0]
    alerted_batches.add(latest_batch)

    return {
        "drift_event": {
            "model_id": "projects/unified-ai-ops/locations/us-central1/models/fraud-classifier-v2",
            "metric": "latency_p99",
            "severity": severity,
            "batch_window": f"batch_{latest_batch}",
            "baseline_value": 40.0,
            "observed_value": round(avg_latency, 2),
            "batch_id": f"batch-{latest_batch}",
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
            "status": f"Drift detected — severity: {severity}"
        }
    }

async def run_pipeline():
    print("=" * 60)
    print("    AEGISOPS — DRIFT WATCHER RUNNING")
    print("=" * 60)
    print(f"Writing drift events to: {OUTPUT_FILE}\n")

    while True:
        event = get_latest_drift_event()

        if event:
            severity = event["drift_event"]["severity"]
            batch = event["drift_event"]["batch_window"]

            with open(OUTPUT_FILE, "w") as f:
                json.dump(event, f, indent=2)

            print(f"[{datetime.now().strftime('%H:%M:%S')}] DRIFT DETECTED — {batch} — {severity.upper()}")
            print(f"    Written to {OUTPUT_FILE}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring... no new drift.")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(run_pipeline())