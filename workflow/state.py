"""Shared state definition for the multi-turn startup conversation."""

from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages


class StartupState(TypedDict):
    """State flowing through every node in the graph."""
    messages: Annotated[list, add_messages]  # Full conversation history
    user_pitch: str                          # Original founder pitch
    turn: int                                # Current conversation turn (1–3)
    max_turns: int                           # Maximum turns (default 3)
    validator_output: str                    # Latest CSO response
    engineer_output: str                     # Latest CTO response
    marketer_output: str                     # Latest CMO response
    final_plan: str                          # Compiled action plan
