"""Shim for adk api_server — loads the actual screening agent from the package."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from forsch.agent_screening.agent import root_agent

agent = root_agent
