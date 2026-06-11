"""
AegisOps — Root Agent Entry Point

This file is required by the ADK CLI tools (`adk web .`, `adk run .`).
It exports `root_agent` which is the configured ADK Agent instance
wired with our custom remediation tools and Arize MCP integration.

Usage:
  adk web .    → Launch the web UI for interactive testing
  adk run .    → Run the agent in the terminal
"""

from dotenv import load_dotenv

# Load .env before any ADK/GenAI imports so GOOGLE_GENAI_API_KEY is available
load_dotenv()

from src.agent.brain import root_agent

# ADK CLI looks for `root_agent` at module level
__all__ = ["root_agent"]
