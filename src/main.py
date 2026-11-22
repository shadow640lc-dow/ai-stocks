import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from colorama import Fore, Style, init
import questionary
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.risk_manager import risk_management_agent
from src.graph.state import AgentState
from src.utils.display import print_trading_output
from src.utils.analysts import ANALYST_ORDER, get_analyst_nodes
from src.utils.progress import progress
from src.utils.visualize import save_graph_as_png
from src.cli.input import (
    parse_cli_inputs,
)
from src.database.database import init_database

import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

# Load environment variables from .env file
load_dotenv()

init(autoreset=True)

# The decision log is written after every run; make sure the local schema
# exists before the portfolio manager tries to insert into it.
init_database()


def parse_hedge_fund_response(response):
    """Parses a JSON string and returns a dictionary."""
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"JSON decoding error: {e}\nResponse: {repr(response)}")
        return None
    except TypeError as e:
        print(f"Invalid response type (expected string, got {type(response).__name__}): {e}")
        return None
    except Exception as e:
        print(f"Unexpected error while parsing response: {e}\nResponse: {repr(response)}")
        return None


##### Run the Hedge Fund #####
def run_hedge_fund(
    tickers: list[str],
    start_date: str,
    end_date: str,
    portfolio: dict,
    show_reasoning: bool = False,
    selected_analysts: list[str] = [],
    model_name: str = "gpt-4.1",
    model_provider: str = "OpenAI",
):
    # Start progress tracking
    progress.start()
    gui_progress = None
    if os.environ.get("MEGATRON_GUI"):
        def gui_progress(agent_name, ticker, status, analysis, timestamp):
            print(
                "@@MEGATRON_PROGRESS@@ "
                + json.dumps(
                    {
                        "agent": agent_name,
                        "ticker": ticker,
                        "status": status,
                        "timestamp": timestamp,
                    }
                ),
                flush=True,
            )

        progress.register_handler(gui_progress)

    try:
        # Build workflow (default to all analysts when none provided)
        workflow = create_workflow(selected_analysts if selected_analysts else None)
        agent = workflow.compile()

        final_state = agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "start_date": start_date,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                },
            },
        )

        return {
            "decisions": parse_hedge_fund_response(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
    finally:
        if gui_progress is not None:
            progress.unregister_handler(gui_progress)
        # Stop progress tracking
        progress.stop()


def start(state: AgentState):
    """Initialize the workflow with the input message."""
    return state


def create_workflow(selected_analysts=None):
    """Create the workflow with selected analysts."""
    workflow = StateGraph(AgentState)
    workflow.add_node("start_node", start)

    # Get analyst nodes from the configuration
    analyst_nodes = get_analyst_nodes()

    # Default to all analysts if none selected
    if selected_analysts is None:
        selected_analysts = list(analyst_nodes.keys())
    # Add selected analyst nodes
    for analyst_key in selected_analysts:
        node_name, node_func = analyst_nodes[analyst_key]
        workflow.add_node(node_name, node_func)
        workflow.add_edge("start_node", node_name)

    # Always add risk and portfolio management
    workflow.add_node("risk_management_agent", risk_management_agent)
    workflow.add_node("portfolio_manager", portfolio_management_agent)

    # Connect selected analysts to risk management
    for analyst_key in selected_analysts:
        node_name = analyst_nodes[analyst_key][0]
        workflow.add_edge(node_name, "risk_management_agent")

    workflow.add_edge("risk_management_agent", "portfolio_manager")
    workflow.add_edge("portfolio_manager", END)

    workflow.set_entry_point("start_node")
    return workflow


def execute_decisions_with_alpaca(
    result: dict,
    mode: str | None,
    tickers: list[str],
) -> None:
    """Place confirmed orders for AI Hedge Fund decisions via Alpaca."""
    from src.execution.alpaca_executor import (
        execute_hedge_fund_decisions,
        estimate_notional,
    )
    from src.utils.alpaca_broker import AlpacaBroker, AlpacaError

    decisions = result.get("decisions") or {}

    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            price = float(
                result["analyst_signals"]["risk_management_agent"][ticker][
                    "current_price"
                ]
            )
        except (KeyError, TypeError, ValueError):
            price = 0.0
        if price > 0:
            prices[ticker] = price

    broker = AlpacaBroker(mode=mode)

    print()
    print(Fore.YELLOW + "⚠  NEXT: ALPACA LIVE EXECUTION (confirmed)" + Style.RESET_ALL)
    print(
        Fore.RED
        + "⚠  You will be asked to approve each order. This places REAL money."
        + Style.RESET_ALL
    )
    print(
        Fore.MAGENTA
        + f"⚠  Target account: {broker.label}"
        + Style.RESET_ALL
    )
    print(
        Fore.MAGENTA
        + f"⚠  Notional price source: {'analyst live prices' if prices else 'MISSING'} "
        + f"({len(prices)}/{len(tickers)} tickers)"
        + Style.RESET_ALL
    )

    def confirm_order(
        ticker: str,
        action: str,
        side: str,
        qty: int,
        notional: float,
    ) -> bool:
        message = (
            f"\n  Place {side.upper()} {qty} x {ticker} "
            f"({action.upper()})"
            + (f"  est ${notional:,.0f}" if notional else "")
            + "?"
        )
        if os.environ.get("MEGATRON_GUI"):
            # The desktop app renders this as a native Yes/No dialog and
            # writes the answer back on stdin. Default remains No.
            print(
                "@@MEGATRON_PROMPT@@ "
                + json.dumps({"kind": "order_approval", "message": message}),
                flush=True,
            )
            try:
                answer = sys.stdin.readline().strip().lower()
            except Exception:
                return False
            return answer in {"y", "yes"}
        return bool(questionary.confirm(message, default=False).ask())

    try:
        results = execute_hedge_fund_decisions(
            decisions=decisions,
            broker=broker,
            confirm=confirm_order,
            prices=prices,
        )
    except AlpacaError as exc:
        print(Fore.RED + f"\n  ✖ {exc}" + Style.RESET_ALL)
        return

    placed = [r for r in results if r["status"] == "placed"]
    print()
    print(
        Fore.GREEN
        + f"  {len(placed)} order(s) submitted to Alpaca "
        + Style.RESET_ALL
        + f"({broker.label})"
    )
    for order in placed:
        print(
            f"    ✓ {order['ticker']} {order['action'].upper()} {order['qty']} "
            f"id={order['order_id']} status={order['order_status']}"
        )


if __name__ == "__main__":
    inputs = parse_cli_inputs(
        description="Run the hedge fund trading system",
        require_tickers=True,
        default_months_back=None,
        include_graph_flag=True,
        include_reasoning_flag=True,
    )

    tickers = inputs.tickers
    selected_analysts = inputs.selected_analysts

    # Construct portfolio here
    portfolio = {
        "cash": inputs.initial_cash,
        "margin_requirement": inputs.margin_requirement,
        "margin_used": 0.0,
        "positions": {
            ticker: {
                "long": 0,
                "short": 0,
                "long_cost_basis": 0.0,
                "short_cost_basis": 0.0,
                "short_margin_used": 0.0,
            }
            for ticker in tickers
        },
        "realized_gains": {
            ticker: {
                "long": 0.0,
                "short": 0.0,
            }
            for ticker in tickers
        },
    }

    result = run_hedge_fund(
        tickers=tickers,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        portfolio=portfolio,
        show_reasoning=inputs.show_reasoning,
        selected_analysts=inputs.selected_analysts,
        model_name=inputs.model_name,
        model_provider=inputs.model_provider,
    )
    print_trading_output(result)

    if inputs.alpaca:
        execute_decisions_with_alpaca(
            result=result,
            mode=inputs.alpaca_mode,
            tickers=tickers,
        )
