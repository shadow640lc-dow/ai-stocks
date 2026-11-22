from datetime import datetime
from typing import Any

from app.backend.services.agent_service import create_agent_function
from app.backend.services.decision_engine import (
    terminal_box,
    terminal_section,
    terminal_style,
)
from src.graph.state import AgentState
from src.utils.analysts import ANALYST_CONFIG


# Analysts Scout should use for alert investigation.
SCOUT_ANALYSTS = [
    "technical_analyst",
    "fundamentals_analyst",
    "growth_analyst",
    "valuation_analyst",
    "sentiment_analyst",
    "news_sentiment_analyst",
]


def _display_name(analyst_key: str) -> str:
    return analyst_key.removesuffix("_analyst").replace("_", " ").upper()


def build_scout_analysts_summary(
    ticker: str,
    result: dict[str, Any],
) -> str:
    """Render a read-only terminal summary of an analyst-run result.

    This formatter intentionally consumes the existing return value only. It
    does not invoke analysts, retrieve data, score opportunities, or trade.
    """
    signals = result.get("analyst_signals", {})
    errors = result.get("analyst_errors", {})
    completed = sum(1 for analyst in SCOUT_ANALYSTS if analyst in signals)
    lines: list[str] = [""]
    lines.extend(
        terminal_box(
            "🤖 AI SCOUT ANALYST GRID  //  ALERT INTELLIGENCE",
            f"{ticker.upper()} · {completed}/{len(SCOUT_ANALYSTS)} ANALYST SIGNALS RECEIVED",
        )
    )
    lines.append(terminal_section("ANALYST NETWORK"))

    for analyst in SCOUT_ANALYSTS:
        name = _display_name(analyst)
        if analyst in errors:
            status = terminal_style("● ERROR", "red", "bold")
            detail = str(errors[analyst])
        elif analyst in signals:
            status = terminal_style("● SIGNAL RECEIVED", "green", "bold")
            detail = "Research signal available in the result payload."
        else:
            status = terminal_style("● NO SIGNAL", "yellow", "bold")
            detail = "No signal was returned by this analyst."

        lines.append(f"  {name:<18} {status}")
        lines.append(terminal_style(f"    └─ {detail}", "muted"))

    lines.append(terminal_style("└" + "─" * 76, "blue"))
    lines.append(terminal_style("  🛡  RESEARCH-ONLY · NO TRADE EXECUTED", "red", "bold"))
    lines.append(terminal_style("└" + "─" * 76, "blue"))
    return "\n".join(lines)


def run_scout_analysts(
    ticker: str,
    market_data: dict[str, Any],
    alert: dict[str, Any],
    model_name: str = "gpt-4.1",
    model_provider: Any = None,
) -> dict[str, Any]:
    """
    Run the existing analyst agents against a Scout alert.

    Scout is research-only.
    This function does not execute trades.

    Scout alerts normally do not contain the historical-analysis dates
    expected by the existing analyst agents, so use the alert dates when
    available and fall back to today's date for the current investigation.
    """

    ticker = ticker.upper().strip()

    # Existing analysts require a valid end_date for financial metrics.
    # TradingView-style Scout alerts may not provide one.
    end_date = alert.get("end_date") or datetime.now().strftime("%Y-%m-%d")
    start_date = alert.get("start_date") or end_date

    state: AgentState = {
        "messages": [],
        "data": {
            "tickers": [ticker],
            "portfolio": {},
            "start_date": start_date,
            "end_date": end_date,
            "market_data": market_data,
            "scout_alert": alert,
            "analyst_signals": {},
            "analyst_errors": {},
        },
        "metadata": {
            "show_reasoning": False,
            "model_name": model_name,
            "model_provider": model_provider,
        },
    }

    for analyst_key in SCOUT_ANALYSTS:
        config = ANALYST_CONFIG.get(analyst_key)

        if not config:
            state["data"]["analyst_errors"][analyst_key] = (
                "Analyst configuration not found."
            )
            continue

        agent_function = config["agent_func"]

        wrapped_agent = create_agent_function(
            agent_function,
            f"scout_{analyst_key}",
        )

        try:
            result = wrapped_agent(state)

            if not result:
                state["data"]["analyst_errors"][analyst_key] = (
                    "Analyst returned no result."
                )
                continue

            # Preserve messages returned by the analyst.
            messages = result.get("messages", [])

            if messages:
                state["messages"].extend(messages)

            # Preserve analyst data returned by the analyst.
            result_data = result.get("data")

            if result_data:
                state["data"].update(result_data)

        except Exception as exc:
            state["data"]["analyst_errors"][analyst_key] = str(exc)

    return {
        "analyst_signals": state["data"].get(
            "analyst_signals",
            {},
        ),
        "analyst_errors": state["data"].get(
            "analyst_errors",
            {},
        ),
    }
