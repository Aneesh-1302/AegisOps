import sys
from google.adk.cli.utils import agent_loader

# Monkey-patch to bypass the hyphen validation
def mock_validate(self, agent_name):
    pass
agent_loader.AgentLoader._validate_agent_name = mock_validate

from google.adk.cli import main

if __name__ == "__main__":
    sys.argv = ["adk", "web", "."]
    sys.exit(main())
