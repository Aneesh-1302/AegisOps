import phoenix as px
from phoenix.otel import register
from opentelemetry import trace
import random
import time

tracer_provider = register(
    project_name="unified-ai-ops",
    endpoint="http://localhost:6006/v1/traces"
)
tracer = trace.get_tracer(__name__)

def send_span(batch_num, scenario):
    with tracer.start_as_current_span("model.predict") as span:

        if scenario == "normal":
            confidence = random.uniform(0.85, 0.99)
            latency_ms = random.uniform(20, 60)
            feature_val = random.gauss(0, 1)
            severity = "none"

        elif scenario == "low":
            # Slight confidence drop, minor latency increase
            confidence = random.uniform(0.70, 0.84)
            latency_ms = random.uniform(60, 120)
            feature_val = random.gauss(1, 1)
            severity = "low"

        elif scenario == "moderate":
            # Noticeable degradation — agent should trigger retraining
            confidence = random.uniform(0.50, 0.69)
            latency_ms = random.uniform(120, 300)
            feature_val = random.gauss(2, 1.5)
            severity = "moderate"

        elif scenario == "critical":
            # Severe — agent should rollback immediately
            confidence = random.uniform(0.20, 0.49)
            latency_ms = random.uniform(500, 1200)
            feature_val = random.gauss(5, 2)
            severity = "critical"

        span.set_attribute("model.id", "fraud-classifier-v2")
        span.set_attribute("model.batch", batch_num)
        span.set_attribute("input.feature_val", feature_val)
        span.set_attribute("output.confidence", confidence)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("drift.severity", severity)
        span.set_attribute("drift.scenario", scenario)

        time.sleep(0.03)

print("Batch 1-2: Normal baseline...")
for batch in range(1, 3):
    for _ in range(20):
        send_span(batch, "normal")
    print(f"  Batch {batch} — normal")

print("Batch 3: Low severity drift...")
for _ in range(20):
    send_span(3, "low")
print("  Batch 3 — LOW drift")

print("Batch 4: Moderate severity drift...")
for _ in range(20):
    send_span(4, "moderate")
print("  Batch 4 — MODERATE drift")

print("Batch 5: Critical severity drift...")
for _ in range(20):
    send_span(5, "critical")
print("  Batch 5 — CRITICAL drift")

print("\nDone. Check http://localhost:6006")
print("Summary:")
print("  Batch 1-2 → severity: none  → agent action: nothing")
print("  Batch 3   → severity: low   → agent action: alert only")
print("  Batch 4   → severity: moderate → agent action: trigger retraining")
print("  Batch 5   → severity: critical → agent action: rollback deployment")