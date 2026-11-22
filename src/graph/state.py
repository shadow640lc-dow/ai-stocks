from typing_extensions import Annotated, Sequence, TypedDict

import operator
from langchain_core.messages import BaseMessage


# ================================================================
# MEGATRON // SHARED AGENT STATE
# ================================================================

def merge_dicts(a: dict[str, any], b: dict[str, any]) -> dict[str, any]:
    """Merge two state dictionaries."""
    return {**a, **b}


# ================================================================
# AGENT STATE
# ================================================================

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    data: Annotated[dict[str, any], merge_dicts]
    metadata: Annotated[dict[str, any], merge_dicts]


# ================================================================
# AGENT REASONING
# ================================================================

def show_agent_reasoning(output, agent_name):
    """
    Handle optional agent reasoning output.

    MEGASTOCKS normally keeps the terminal clean and lets the
    final display renderer present the polished research results.

    Raw JSON is intentionally NOT printed here.

    Agents can still call this function when --show-reasoning
    is enabled without breaking the workflow.
    """

    # Keep this function intentionally quiet.
    #
    # The previous implementation printed:
    #
    #     ========== Agent Name ==========
    #     { giant JSON response }
    #
    # That created duplicate/raw terminal output because the
    # final MEGATRON renderer already displays the useful results.
    #
    # Reasoning remains available inside the returned analysis
    # objects and can be rendered by the dedicated display layer.

    return None
