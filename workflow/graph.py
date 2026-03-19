"""
LangGraph multi-turn conversation graph.

Each turn: Validator → Engineer → Marketer (all 3 see the full conversation).
After 3 turns, a plan compiler produces the final action plan.

Graph structure:
  ┌─────────────────────────────────────────┐
  │          validator ──► engineer          │
  │              ▲            │              │
  │              │            ▼              │
  │          router ◄──── marketer          │
  │           │                              │
  │     (turn < max?)                        │
  │      yes → loop    no → plan_compiler   │
  │                           │              │
  │                          END             │
  └─────────────────────────────────────────┘
"""

import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langgraph.graph import END, StateGraph

from skills import VALIDATOR_SKILL, ENGINEER_SKILL, MARKETER_SKILL
from workflow.state import StartupState

load_dotenv()


# ── LLM ──────────────────────────────────────────────────────────────

def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_ENDPOINT"),
        api_key=os.getenv("AZURE_API_KEY"),
        azure_deployment=os.getenv("DEPLOYMENT_NAME"),
        api_version=os.getenv("API_VERSION"),
        temperature=0.7,
    )


# ── Helper: build conversation context ───────────────────────────────

def _get_msg_field(msg, field: str, default: str = "") -> str:
    """Safely extract a field from a message (works with both dicts and LangChain message objects)."""
    if hasattr(msg, field):
        return getattr(msg, field)
    if isinstance(msg, dict):
        return msg.get(field, default)
    return default


def _build_conversation_context(state: StartupState) -> str:
    """Render prior conversation so each agent sees the full thread."""
    lines = []
    for msg in state["messages"]:
        # LangChain message objects use .type ("human"/"ai"), dicts use "role"
        role = _get_msg_field(msg, "type", "")
        if not role:
            role = _get_msg_field(msg, "role", "")
        content = _get_msg_field(msg, "content", "")

        if role in ("user", "human"):
            lines.append(f"[FOUNDER]: {content}")
        elif role in ("assistant", "ai"):
            lines.append(f"{content}")
    return "\n\n---\n\n".join(lines)


# ── Agent Nodes ───────────────────────────────────────────────────────

def _agent_node(state: StartupState, skill: dict, turn_label: str) -> dict:
    """Generic agent node — calls the LLM with the skill's system prompt + conversation."""
    llm = get_llm()
    turn = state["turn"]
    conversation = _build_conversation_context(state)

    user_msg = f"""This is **Turn {turn} of {state["max_turns"]}**.

## Original Pitch
{state["user_pitch"]}

## Conversation So Far
{conversation}

---

Now respond as the {skill["title"]}. Address the other team members' points directly.
{"This is the FINAL turn. You MUST converge and list your specific ownership items for the action plan." if turn == state["max_turns"] else "Challenge, refine, and push the conversation forward."}"""

    response = llm.invoke([
        {"role": "system", "content": skill["system_prompt"]},
        {"role": "user", "content": user_msg},
    ])

    output = response.content
    tagged = f"{skill['emoji']} **{skill['title'].upper()} ({skill['name']}) — Turn {turn}**\n\n{output}"

    # Determine which output field to update
    field_map = {
        "startup-validator": "validator_output",
        "senior-engineer": "engineer_output",
        "growth-marketer": "marketer_output",
    }

    return {
        "messages": [{"role": "assistant", "content": tagged}],
        field_map[skill["name"]]: output,
    }


def validator_node(state: StartupState) -> dict:
    return _agent_node(state, VALIDATOR_SKILL, "CSO")


def engineer_node(state: StartupState) -> dict:
    return _agent_node(state, ENGINEER_SKILL, "CTO")


def marketer_node(state: StartupState) -> dict:
    return _agent_node(state, MARKETER_SKILL, "CMO")


def router_node(state: StartupState) -> dict:
    """Increment the turn counter after all 3 agents have spoken."""
    return {"turn": state["turn"] + 1}


def plan_compiler_node(state: StartupState) -> dict:
    """Compile the final action plan from all 3 agents' last outputs."""
    llm = get_llm()

    responsibilities = {
        "CSO": VALIDATOR_SKILL["plan_responsibilities"],
        "CTO": ENGINEER_SKILL["plan_responsibilities"],
        "CMO": MARKETER_SKILL["plan_responsibilities"],
    }

    resp_text = ""
    for role, items in responsibilities.items():
        resp_text += f"\n**{role} default responsibilities:**\n"
        for item in items:
            resp_text += f"  - {item}\n"

    prompt = f"""You are a startup plan compiler. You have just witnessed a 3-turn conversation between a CSO, CTO, and CMO about building a satellite imagery company.

## Original Pitch
{state["user_pitch"]}

## CSO's Final Analysis
{state["validator_output"]}

## CTO's Final Technical Plan
{state["engineer_output"]}

## CMO's Final Marketing Strategy
{state["marketer_output"]}

## Default Responsibility Areas
{resp_text}

---

Now produce the **FINAL STARTUP ACTION PLAN** with these sections:

### 1. Company Summary (3 sentences max)

### 2. Validated Problem & Customer Segment

### 3. Action Plan Table
Create a markdown table with columns: Task | Owner (CSO/CTO/CMO) | Timeline | Priority (P0/P1/P2) | Dependencies
Include at least 15 specific tasks spanning all three roles.

### 4. Week 1 Sprint
What each person does in the first 7 days.

### 5. Key Risks & Mitigations (top 5)

### 6. Success Metrics
Define 3 measurable milestones for the first 30 days.

Be specific. No hand-waving. Every task must have a clear owner."""

    response = llm.invoke([{"role": "user", "content": prompt}])
    plan = response.content

    return {
        "messages": [{"role": "assistant", "content": f"💡 **FINAL ACTION PLAN**\n\n{plan}"}],
        "final_plan": plan,
    }


# ── Routing Logic ─────────────────────────────────────────────────────

def should_continue(state: StartupState) -> str:
    """After router: loop back to validator or proceed to plan."""
    if state["turn"] <= state["max_turns"]:
        return "validator"
    return "plan_compiler"


# ── Graph Construction ────────────────────────────────────────────────

def build_workflow() -> object:
    """Build and compile the multi-turn startup conversation graph."""
    graph = StateGraph(StartupState)

    # Add nodes
    graph.add_node("validator", validator_node)
    graph.add_node("engineer", engineer_node)
    graph.add_node("marketer", marketer_node)
    graph.add_node("router", router_node)
    graph.add_node("plan_compiler", plan_compiler_node)

    # Entry point
    graph.set_entry_point("validator")

    # Edges: within each turn, agents go in sequence
    graph.add_edge("validator", "engineer")
    graph.add_edge("engineer", "marketer")
    graph.add_edge("marketer", "router")

    # Conditional: loop or compile plan
    graph.add_conditional_edges("router", should_continue, {
        "validator": "validator",
        "plan_compiler": "plan_compiler",
    })

    graph.add_edge("plan_compiler", END)

    return graph.compile()


# ── Runners ───────────────────────────────────────────────────────────

def run_startup_workflow(pitch: str, max_turns: int = 3) -> dict:
    """Run the full multi-turn workflow and return final state."""
    app = build_workflow()
    initial_state = {
        "messages": [{"role": "user", "content": pitch}],
        "user_pitch": pitch,
        "turn": 1,
        "max_turns": max_turns,
        "validator_output": "",
        "engineer_output": "",
        "marketer_output": "",
        "final_plan": "",
    }
    return app.invoke(initial_state)


def stream_startup_workflow(pitch: str, max_turns: int = 3):
    """Stream the workflow, yielding (node_name, output) per step."""
    app = build_workflow()
    initial_state = {
        "messages": [{"role": "user", "content": pitch}],
        "user_pitch": pitch,
        "turn": 1,
        "max_turns": max_turns,
        "validator_output": "",
        "engineer_output": "",
        "marketer_output": "",
        "final_plan": "",
    }
    for event in app.stream(initial_state):
        for node_name, node_output in event.items():
            yield node_name, node_output
