import asyncio
import json
import os
import sys

from dotenv import load_dotenv

# Load environment variables so the Gemini API key is available
load_dotenv()

# Import the programmatic entry point
from src.agent.brain import evaluate_telemetry

FILE_TO_WATCH = "latest_drift_event.json"
POLL_INTERVAL_SECONDS = 3

async def watch_loop():
    print("=" * 60)
    print("    AEGISOPS — AUTONOMOUS DAEMON RUNNING")
    print("=" * 60)
    print(f"Listening for updates to {FILE_TO_WATCH}...\n")

    last_mtime = None

    # Get initial modified time so we don't process a stale event on boot
    if os.path.exists(FILE_TO_WATCH):
        last_mtime = os.path.getmtime(FILE_TO_WATCH)

    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

        if not os.path.exists(FILE_TO_WATCH):
            continue

        current_mtime = os.path.getmtime(FILE_TO_WATCH)

        if last_mtime is None or current_mtime > last_mtime:
            # File has been modified!
            last_mtime = current_mtime

            print("\n" + "━" * 60)
            print(f"🤖 [DAEMON] Detected update to {FILE_TO_WATCH}! Waking up Agent...")
            print("━" * 60)

            try:
                with open(FILE_TO_WATCH, "r") as f:
                    data = f.read()
                
                # Verify it's actually valid JSON
                json.loads(data)

                # Programmatically feed the JSON straight into the agent
                await evaluate_telemetry(telemetry_context=data)

            except json.JSONDecodeError:
                print(f"⚠️  [DAEMON] Warning: {FILE_TO_WATCH} is not valid JSON. Ignoring.")
            except Exception as e:
                print(f"❌ [DAEMON] Error processing event: {e}")
            
            print(f"\n[DAEMON] Agent execution finished. Resuming background monitoring...\n")


if __name__ == "__main__":
    try:
        asyncio.run(watch_loop())
    except KeyboardInterrupt:
        print("\nDaemon stopped.")
        sys.exit(0)
