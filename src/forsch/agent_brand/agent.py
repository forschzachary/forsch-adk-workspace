"""brand agent definition."""

from google.adk import Agent

agent = Agent(
    name="brand_agent",
    model="gemini-2.5-flash",
    instruction="You are the brand team lead for Forsch.",
)
