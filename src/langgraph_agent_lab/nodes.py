"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""
from __future__ import annotations

import os

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from .state import AgentState, make_event


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM."""
    query = state.get("query", "")
    route = "simple"
    risk_level = "low"
    
    # Priority heuristics for safe fallback if LLM key is not provided yet
    query_lower = query.lower()
    if any(kw in query_lower for kw in ["refund", "delete", "cancel", "email"]):
        route = "risky"
        risk_level = "high"
    elif any(kw in query_lower for kw in ["status", "lookup", "order", "track"]):
        route = "tool"
    elif any(kw in query_lower for kw in ["fix it", "can you fix", "help me fix"]):
        route = "missing_info"
    elif any(kw in query_lower for kw in ["timeout", "failure", "error", "crash"]):
        route = "error"
        
    try:
        from .llm import get_llm
        llm = get_llm()
        
        class Classification(BaseModel):
            route: str = Field(description="Must be one of: simple, tool, missing_info, risky, error.")
            risk_level: str = Field(description="Must be 'high' if route is 'risky', else 'low'.")
            
        structured_llm = llm.with_structured_output(Classification)
        prompt = (
            f"Classify the following customer query: \"{query}\"\n\n"
            "Categories:\n"
            "- risky: Actions with side effects like refunds, deletions, sending emails, or account cancellations.\n"
            "- tool: Information lookups, order status, tracking info, database search queries.\n"
            "- missing_info: Vague or incomplete queries lacking actionable context (e.g. 'Can you fix it?').\n"
            "- error: System failures, timeouts, crashes, service unavailable.\n"
            "- simple: General questions answerable without tools/actions (e.g. 'How do I reset my password?').\n\n"
            "Respect this priority: risky > tool > missing_info > error > simple.\n"
            "If the category is risky, risk_level must be 'high', otherwise 'low'."
        )
        decision = structured_llm.invoke(prompt)
        if decision and hasattr(decision, "route"):
            route = decision.route
            risk_level = decision.risk_level
    except Exception:
        pass
        
    return {
        "route": route,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"classified query as {route}")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call."""
    attempt = state.get("attempt", 0)
    route = state.get("route", "")
    
    if route == "error" and attempt < 2:
        result_string = "ERROR: Transient database timeout failure."
    else:
        result_string = "SUCCESS: Order lookup/action processed successfully."
        
    return {
        "tool_results": [result_string],
        "events": [make_event("tool", "completed", f"executed mock tool on attempt {attempt}")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate."""
    tool_results = state.get("tool_results", [])
    latest_result = tool_results[-1] if tool_results else ""
    
    res = "success"
    if "ERROR" in latest_result or "timeout" in latest_result.lower() or "failure" in latest_result.lower():
        res = "needs_retry"
        
    try:
        from .llm import get_llm
        llm = get_llm()
        
        class Evaluation(BaseModel):
            evaluation_result: str = Field(description="Must be 'success' or 'needs_retry'.")
            reason: str = Field(description="Reason for evaluation.")
            
        structured_llm = llm.with_structured_output(Evaluation)
        prompt = (
            f"Evaluate the latest tool execution output for a customer support query.\n"
            f"Tool output: \"{latest_result}\"\n\n"
            f"Determine if the tool call succeeded ('success') or failed due to an error/timeout ('needs_retry')."
        )
        eval_output = structured_llm.invoke(prompt)
        if eval_output and hasattr(eval_output, "evaluation_result"):
            res = eval_output.evaluation_result
    except Exception:
        pass
        
    return {
        "evaluation_result": res,
        "events": [make_event("evaluate", "completed", f"tool evaluation: {res}")],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM."""
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval", {})
    
    context = f"Query: {query}\n"
    if tool_results:
        context += f"Tool Results: {tool_results}\n"
    if approval:
        context += f"Approval Decision: {approval}\n"
        
    try:
        from .llm import get_llm
        llm = get_llm()
        prompt = (
            f"Generate a helpful support response grounded in the provided context.\n"
            f"Context:\n{context}\n\n"
            f"Response:"
        )
        response = llm.invoke(prompt)
        final_answer = response.content
    except Exception:
        final_answer = f"Hello. Here is the response to your request: {query}. The action was processed."
        
    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "generated final response")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    try:
        from .llm import get_llm
        llm = get_llm()
        prompt = (
            f"The user query is too vague: \"{query}\".\n"
            f"Generate a polite clarification question asking for specific details to help resolve their request.\n"
            f"Clarification Question:"
        )
        response = llm.invoke(prompt)
        pending_question = response.content
    except Exception:
        pending_question = "Could you please provide more details or an order number so we can help you?"
        
    return {
        "pending_question": pending_question,
        "final_answer": pending_question,
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    try:
        from .llm import get_llm
        llm = get_llm()
        prompt = (
            f"Describe the proposed action for the query \"{query}\" and why it requires human verification/approval.\n"
            f"Proposed Action Description:"
        )
        response = llm.invoke(prompt)
        proposed_action = response.content
    except Exception:
        proposed_action = f"Perform transaction for query: {query}. Requires confirmation due to high risk."
        
    return {
        "proposed_action": proposed_action,
        "events": [make_event("risky_action", "completed", "prepared risky action")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step."""
    if os.getenv("LANGGRAPH_INTERRUPT") == "true":
        if state.get("approval"):
            return {
                "events": [make_event("approval", "completed", "reused approval from state")],
            }
            
        decision_payload = interrupt(
            {
                "message": f"Approval required for proposed action: {state.get('proposed_action')}",
                "proposed_action": state.get("proposed_action"),
            }
        )
        
        approved = False
        comment = ""
        if isinstance(decision_payload, dict):
            approved = decision_payload.get("approved", False)
            comment = decision_payload.get("comment", "")
        elif isinstance(decision_payload, bool):
            approved = decision_payload
            
        approval_decision = {"approved": approved, "reviewer": "human-reviewer", "comment": comment}
        return {
            "approval": approval_decision,
            "events": [make_event("approval", "completed", f"HITL decision: {approved}")],
        }
    else:
        approval_decision = {"approved": True, "reviewer": "mock-reviewer", "comment": "Auto-approved"}
        return {
            "approval": approval_decision,
            "events": [make_event("approval", "completed", "auto-approved")],
        }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt."""
    attempt = state.get("attempt", 0) + 1
    err_msg = f"Attempt {attempt} failed."
    return {
        "attempt": attempt,
        "errors": [err_msg],
        "events": [make_event("retry", "completed", f"retry attempt {attempt}")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    errors = state.get("errors", [])
    latest_error = errors[-1] if errors else "Unknown failure"
    final_answer = f"We are sorry, but your request could not be completed after multiple attempts. Error details: {latest_error}."
    return {
        "final_answer": final_answer,
        "events": [make_event("dead_letter", "completed", "exhausted retries")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
