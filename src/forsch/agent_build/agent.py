"""build agent definition."""

from google.adk import Agent

agent = Agent(
    name="build_agent",
    model="gemini-2.5-flash",
    instruction="You are the build team lead for Forsch.",
)
