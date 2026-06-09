"""
AegisOps — Orchestrator (main.py)

Simplified entry point for the ADK-based agent:
  1. Loads environment configuration (.env)
  2. Imports the pre-built ADK agent from brain.py
  3. Launches the interactive demo loop

For the web UI, use `adk web .` from the project root instead.
"""

import asyncio

from dotenv import load_dotenv

# ── Load environment before any ADK imports ───────────────────────────────
load_dotenv()

from .agent.brain import root_agent, run_agent_loop


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def main():
    """Boot the AegisOps in CLI demo mode."""
    print("=" * 60)
    print("    AegisOps — ADK v2.2")
    print("=" * 60)
    print(f"    Agent: {root_agent.name}")
    print(f"    Model: {root_agent.model}")
    print(f"     Tools: {len(root_agent.tools)} registered")
    print("=" * 60)

    # Launch the interactive demo loop
    await run_agent_loop(agent=root_agent)


if __name__ == "__main__":
    asyncio.run(main())
