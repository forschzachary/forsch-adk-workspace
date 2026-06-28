"""Shim to expose root_agent from the package structure for adk api_server."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, "/root/.hermes/workspace/adk/components/src")
from forsch.agent_agent_logic_specialist.agent import root_agent
