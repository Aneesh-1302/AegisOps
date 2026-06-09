import phoenix as px
from phoenix.otel import register
from opentelemetry import trace
import random
import time

# Connect to your running Phoenix instance
tracer_provider = register(
    project_name="unified-ai-ops",
    endpoint="http://localhost:6006/v1/traces"
)
tracer = trace.get_tracer(__name__)

def simulate_prediction(batch_num, inject_drift=False):
    with tracer.start_as_current_span("model.predict") as span:
        # Simulate input features
        feature_val = random.gauss(0, 1) if not inject_drift else random.gauss(3, 2)
        prediction = random.choice([0, 1])
        confidence = random.uniform(0.85, 0.99) if not inject_drift else random.uniform(0.45, 0.65)
        latency_ms = random.uniform(20, 60) if not inject_drift else random.uniform(200, 600)

        span.set_attribute("model.id", "fraud-classifier-v2")
        span.set_attribute("model.batch", batch_num)
        span.set_attribute("input.feature_val", feature_val)
        span.set_attribute("output.prediction", prediction)
        span.set_attribute("output.confidence", confidence)
        span.set_attribute("latency_ms", latency_ms)
        span.set_attribute("drift_injected", inject_drift)

        time.sleep(0.05)

print("Sending normal traces (batches 1-3)...")
for batch in range(1, 4):
    for _ in range(20):
        simulate_prediction(batch_num=batch, inject_drift=False)
    print(f"  Batch {batch} done")

print("Injecting drift (batches 4-6)...")
for batch in range(4, 7):
    for _ in range(20):
        simulate_prediction(batch_num=batch, inject_drift=True)
    print(f"  Batch {batch} done — DRIFT INJECTED")

print("Done. Check http://localhost:6006")