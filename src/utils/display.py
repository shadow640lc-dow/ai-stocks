# ================================================================
# MEGASTOCKS // NEON BLUE TERMINAL PALETTE
# ================================================================
#
# Keep the existing Fore/Style API so every legacy renderer continues
# to work, but route it through the unified MEGATRON palette.
#
class _NeonFore:
    BLUE = "\033[38;5;39m"
    CYAN = "\033[38;5;51m"
    GREEN = "\033[38;5;46m"
    YELLOW = "\033[38;5;220m"
    RED = "\033[38;5;203m"
    WHITE = "\033[97m"
    MAGENTA = "\033[38;5;213m"
    RESET = "\033[0m"


class _NeonStyle:
    BRIGHT = "\033[1m"
    RESET_ALL = "\033[0m"


Fore = _NeonFore()
Style = _NeonStyle()

from tabulate import tabulate
from .analysts import ANALYST_ORDER
import math
import os
import json
import re
import sys
import textwrap


def sort_agent_signals(signals):
    """Sort agent signals in a consistent order."""
    # Create order mapping from ANALYST_ORDER
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    analyst_order["Risk Management"] = len(ANALYST_ORDER)  # Add Risk Management at the end

    return sorted(signals, key=lambda x: analyst_order.get(x[0], 999))


def _legacy_print_trading_output(result: dict) -> None:
    """
    Print formatted trading results with colored tables for multiple tickers.

    Args:
        result (dict): Dictionary containing decisions and analyst signals for multiple tickers
    """
    decisions = result.get("decisions")
    if not decisions:
        print(f"{Fore.RED}No trading decisions available{Style.RESET_ALL}")
        return

    # Print decisions for each ticker
    for ticker, decision in decisions.items():
        print(f"\n{Fore.WHITE}{Style.BRIGHT}Analysis for {Fore.CYAN}{ticker}{Style.RESET_ALL}")
        print(f"{Fore.BLUE}{Style.BRIGHT}{'=' * 50}{Style.RESET_ALL}")

        # Prepare analyst signals table for this ticker
        table_data = []
        for agent, signals in result.get("analyst_signals", {}).items():
            if ticker not in signals:
                continue

            # Skip Risk Management agent in the signals section
            if agent == "risk_management_agent":
                continue

            signal = signals[ticker]
            agent_name = agent.replace("_agent", "").replace("_", " ").title()
            signal_type = signal.get("signal", "").upper()
            confidence = signal.get("confidence", 0)

            signal_color = {
                "BULLISH": Fore.GREEN,
                "BEARISH": Fore.RED,
                "NEUTRAL": Fore.YELLOW,
            }.get(signal_type, Fore.WHITE)

            # Get reasoning if available
            reasoning_str = ""
            if "reasoning" in signal and signal["reasoning"]:
                reasoning = signal["reasoning"]

                # Handle different types of reasoning (string, dict, etc.)
                if isinstance(reasoning, str):
                    reasoning_str = reasoning
                elif isinstance(reasoning, dict):
                    # Convert dict to string representation
                    reasoning_str = json.dumps(reasoning, indent=2)
                else:
                    # Convert any other type to string
                    reasoning_str = str(reasoning)

                # Wrap long reasoning text to make it more readable
                wrapped_reasoning = ""
                current_line = ""
                # Use a fixed width of 60 characters to match the table column width
                max_line_length = 60
                for word in reasoning_str.split():
                    if len(current_line) + len(word) + 1 > max_line_length:
                        wrapped_reasoning += current_line + "\n"
                        current_line = word
                    else:
                        if current_line:
                            current_line += " " + word
                        else:
                            current_line = word
                if current_line:
                    wrapped_reasoning += current_line

                reasoning_str = wrapped_reasoning

            table_data.append(
                [
                    f"{Fore.CYAN}{agent_name}{Style.RESET_ALL}",
                    f"{signal_color}{signal_type}{Style.RESET_ALL}",
                    f"{Fore.WHITE}{confidence}%{Style.RESET_ALL}",
                    f"{Fore.WHITE}{reasoning_str}{Style.RESET_ALL}",
                ]
            )

        # Sort the signals according to the predefined order
        table_data = sort_agent_signals(table_data)

        print(f"\n{Fore.WHITE}{Style.BRIGHT}AGENT ANALYSIS:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(
            tabulate(
                table_data,
                headers=[f"{Fore.WHITE}Agent", "Signal", "Confidence", "Reasoning"],
                tablefmt="grid",
                colalign=("left", "center", "right", "left"),
            )
        )

        # Print Trading Decision Table
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        # Get reasoning and format it
        reasoning = decision.get("reasoning", "")
        # Wrap long reasoning text to make it more readable
        wrapped_reasoning = ""
        if reasoning:
            current_line = ""
            # Use a fixed width of 60 characters to match the table column width
            max_line_length = 60
            for word in reasoning.split():
                if len(current_line) + len(word) + 1 > max_line_length:
                    wrapped_reasoning += current_line + "\n"
                    current_line = word
                else:
                    if current_line:
                        current_line += " " + word
                    else:
                        current_line = word
            if current_line:
                wrapped_reasoning += current_line

        decision_data = [
            ["Action", f"{action_color}{action}{Style.RESET_ALL}"],
            ["Quantity", f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}"],
            [
                "Confidence",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
            ],
            ["Reasoning", f"{Fore.WHITE}{wrapped_reasoning}{Style.RESET_ALL}"],
        ]

        print(f"\n{Fore.WHITE}{Style.BRIGHT}TRADING DECISION:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(tabulate(decision_data, tablefmt="grid", colalign=("left", "left")))

    # Print Portfolio Summary
    print(f"\n{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY:{Style.RESET_ALL}")
    portfolio_data = []

    # Extract portfolio manager reasoning (common for all tickers)
    portfolio_manager_reasoning = None
    for ticker, decision in decisions.items():
        if decision.get("reasoning"):
            portfolio_manager_reasoning = decision.get("reasoning")
            break

    analyst_signals = result.get("analyst_signals", {})
    for ticker, decision in decisions.items():
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        # Calculate analyst signal counts
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        if analyst_signals:
            for agent, signals in analyst_signals.items():
                if ticker in signals:
                    signal = signals[ticker].get("signal", "").upper()
                    if signal == "BULLISH":
                        bullish_count += 1
                    elif signal == "BEARISH":
                        bearish_count += 1
                    elif signal == "NEUTRAL":
                        neutral_count += 1

        portfolio_data.append(
            [
                f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
                f"{action_color}{action}{Style.RESET_ALL}",
                f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
                f"{Fore.GREEN}{bullish_count}{Style.RESET_ALL}",
                f"{Fore.RED}{bearish_count}{Style.RESET_ALL}",
                f"{Fore.YELLOW}{neutral_count}{Style.RESET_ALL}",
            ]
        )

    headers = [
        f"{Fore.WHITE}Ticker",
        f"{Fore.WHITE}Action",
        f"{Fore.WHITE}Quantity",
        f"{Fore.WHITE}Confidence",
        f"{Fore.WHITE}Bullish",
        f"{Fore.WHITE}Bearish",
        f"{Fore.WHITE}Neutral",
    ]

    # Print the portfolio summary table
    print(
        tabulate(
            portfolio_data,
            headers=headers,
            tablefmt="grid",
            colalign=("left", "center", "right", "right", "center", "center", "center"),
        )
    )

    # Print Portfolio Manager's reasoning if available
    if portfolio_manager_reasoning:
        # Handle different types of reasoning (string, dict, etc.)
        reasoning_str = ""
        if isinstance(portfolio_manager_reasoning, str):
            reasoning_str = portfolio_manager_reasoning
        elif isinstance(portfolio_manager_reasoning, dict):
            # Convert dict to string representation
            reasoning_str = json.dumps(portfolio_manager_reasoning, indent=2)
        else:
            # Convert any other type to string
            reasoning_str = str(portfolio_manager_reasoning)

        # Wrap long reasoning text to make it more readable
        wrapped_reasoning = ""
        current_line = ""
        # Use a fixed width of 60 characters to match the table column width
        max_line_length = 60
        for word in reasoning_str.split():
            if len(current_line) + len(word) + 1 > max_line_length:
                wrapped_reasoning += current_line + "\n"
                current_line = word
            else:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
        if current_line:
            wrapped_reasoning += current_line

        print(f"\n{Fore.WHITE}{Style.BRIGHT}Portfolio Strategy:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{wrapped_reasoning}{Style.RESET_ALL}")


# ================================================================
# NEON RESEARCH TERMINAL
# ================================================================

TERMINAL_WIDTH = 74
_ANSI = {
    "blue": "\033[38;5;39m",
    "cyan": "\033[38;5;51m",
    "green": "\033[38;5;46m",
    "yellow": "\033[38;5;220m",
    "red": "\033[38;5;203m",
    "muted": "\033[38;5;245m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}


def _terminal_style(text: str, *styles: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return "".join(_ANSI[style] for style in styles) + text + _ANSI["reset"]


def terminal_box(title: str, subtitle: str | None = None) -> list[str]:
    lines = [
        _terminal_style("╔" + "═" * TERMINAL_WIDTH + "╗", "blue"),
        _terminal_style("║" + f"  {title}".ljust(TERMINAL_WIDTH) + "║", "blue"),
    ]
    if subtitle:
        lines.append(_terminal_style("║" + f"  {subtitle}".ljust(TERMINAL_WIDTH) + "║", "blue"))
    lines.append(_terminal_style("╚" + "═" * TERMINAL_WIDTH + "╝", "blue"))
    return lines


def terminal_section(title: str) -> str:
    return _terminal_style(f"┌─ {title}", "blue", "bold")


def score_bar(value: object, width: int = 12) -> str:
    try:
        score = max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        score = 0.0
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


def status_style(signal: object) -> tuple[str, str]:
    value = str(signal or "NEUTRAL").upper()
    if value == "BULLISH":
        return "🟢 BULLISH", "green"
    if value == "BEARISH":
        return "🔴 BEARISH", "red"
    return "🟡 NEUTRAL", "yellow"


def _display_name(agent: object) -> str:
    return str(agent).replace("_agent", "").replace("_", " ").title()


def _confidence(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _wrap(value: object, width: int = 68, limit: int = 5) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    lines = []
    for paragraph in text.splitlines() or [text]:
        lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=False) or [""])
    if len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = lines[-1].rstrip(" .") + " …"
    return lines


def _scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


_METRIC_LABELS = {
    "adx": "ADX (14)",
    "trend_strength": "Trend Strength",
    "z_score": "Z-Score (50D)",
    "price_vs_bb": "Price vs Bollinger",
    "rsi_14": "RSI (14)",
    "rsi_28": "RSI (28)",
    "momentum_1m": "Momentum 1M",
    "momentum_3m": "Momentum 3M",
    "momentum_6m": "Momentum 6M",
    "volume_momentum": "Volume Momentum",
    "historical_volatility": "Historical Volatility",
    "volatility_regime": "Volatility Regime",
    "volatility_z_score": "Volatility Z-Score",
    "atr_ratio": "ATR / Price",
    "hurst_exponent": "Hurst Exponent",
    "skewness": "Skewness",
    "kurtosis": "Kurtosis",
    "total_articles": "Total Articles",
    "bullish_articles": "Bullish Articles",
    "bearish_articles": "Bearish Articles",
    "neutral_articles": "Neutral Articles",
    "articles_classified_by_llm": "LLM Classified",
    "total_trades": "Total Trades",
    "bullish_trades": "Bullish Trades",
    "bearish_trades": "Bearish Trades",
    "weight": "Weight",
    "weighted_bullish": "Weighted Bullish",
    "weighted_bearish": "Weighted Bearish",
    "total_weighted_bullish": "Total Weighted Bullish",
    "total_weighted_bearish": "Total Weighted Bearish",
    "signal_determination": "Determination",
    "profitability_signal": "Profitability Signal",
    "growth_signal": "Growth Signal",
    "financial_health_signal": "Financial Health Signal",
    "price_ratios_signal": "Price Ratios Signal",
}

# Ratios stored as 0–1 are rendered as percentages; confidence is already 0–100.
_PERCENT_METRICS = {
    "trend_strength",
    "price_vs_bb",
    "momentum_1m",
    "momentum_3m",
    "momentum_6m",
    "historical_volatility",
    "atr_ratio",
    "weight",
}
_RATIO_METRICS = {"volume_momentum", "volatility_regime"}
_ARTICLE_COUNTS = {"bullish_articles", "bearish_articles", "neutral_articles", "articles_classified_by_llm"}
_TRADE_COUNTS = {"bullish_trades", "bearish_trades"}


def _metric_label(key: object) -> str:
    return _METRIC_LABELS.get(str(key), str(key).replace("_", " ").title())


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _metric_value(key: str, value: object, context: dict) -> str:
    """One readable value; never a Python dict/list repr."""
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        text = value.strip()
        return text.upper() if key == "signal" and text else text or "n/a"

    number = _number(value)
    if number is None:
        return str(value)

    if key == "confidence":
        return f"{number:.1f}%"
    if key in _PERCENT_METRICS:
        sign = "+" if key.startswith("momentum") else ""
        return f"{number * 100:{sign}.2f}%"
    if key in _RATIO_METRICS:
        return f"{number:.2f}×"
    if key in _ARTICLE_COUNTS:
        total = _number(context.get("total_articles"))
        if total:
            return f"{int(number):,}  ({number / total * 100:.1f}%)"
        return f"{int(number):,}"
    if key in _TRADE_COUNTS:
        total = _number(context.get("total_trades"))
        if total:
            return f"{int(number):,}  ({number / total * 100:.1f}%)"
        return f"{int(number):,}"
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    if number != 0 and abs(number) < 0.001:
        return f"{number:.2e}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def _detail_pairs(text: str) -> list[tuple[str, str]]:
    """Split 'ROE: 1%, Net Margin: 2%' into report rows."""
    if ", " not in text or ":" not in text:
        return []
    pairs: list[tuple[str, str]] = []
    for part in text.split(", "):
        match = re.match(r"^([A-Za-z][A-Za-z0-9 /&().%_\-]{1,28}):\s*(.+)$", part.strip())
        if not match:
            return []
        pairs.append((match.group(1), match.group(2)))
    return pairs if len(pairs) > 1 else []


def _reasoning_rows(mapping: dict, indent: int = 2) -> list[str]:
    lines: list[str] = []
    for key, value in mapping.items():
        label = _metric_label(key)
        pad = " " * indent
        if isinstance(value, dict):
            if key == "metrics":
                # Metrics belong to the group heading above them.
                lines.extend(_reasoning_rows(value, indent))
            else:
                lines.append(_terminal_style(f"{pad}{label.upper()}", "cyan", "bold"))
                lines.extend(_reasoning_rows(value, indent + 2))
            continue

        if isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{pad}{label:<26} n/a")
                continue
            rendered = " · ".join(_metric_value(str(key), item, mapping) for item in value if _scalar(item))
            if not rendered:
                rendered = f"{len(value)} items"
            for index, text in enumerate(_wrap(rendered, width=52, limit=4)):
                prefix = f"{pad}{label:<26} " if index == 0 else " " * (indent + 27)
                lines.append(prefix + text)
            continue

        if isinstance(value, str):
            pairs = _detail_pairs(value)
            if pairs:
                lines.extend(f"{pad}{sub_label:<26} {sub_value}" for sub_label, sub_value in pairs)
                continue

        text = _metric_value(str(key), value, mapping)
        if isinstance(value, str) and len(text) > 52:
            for index, line in enumerate(_wrap(text, width=52, limit=4)):
                prefix = f"{pad}{label:<26} " if index == 0 else " " * (indent + 27)
                lines.append(prefix + line)
        else:
            lines.append(f"{pad}{label:<26} {text}")
    return lines


def _format_reasoning(reasoning: object) -> list[str]:
    """Render nested research metrics as human-readable report rows."""
    if not isinstance(reasoning, dict):
        return [f"  {line}" for line in _wrap(reasoning)]
    return _reasoning_rows(reasoning, 2)


def _signals_for_ticker(result: dict, ticker: str) -> list[tuple[str, dict]]:
    order = {key: index for index, (_, key) in enumerate(ANALYST_ORDER)}
    rows: list[tuple[str, dict]] = []
    for agent, by_ticker in result.get("analyst_signals", {}).items():
        if agent.startswith("risk_management_agent") or not isinstance(by_ticker, dict):
            continue
        signal = by_ticker.get(ticker)
        if isinstance(signal, dict):
            rows.append((agent, signal))
    return sorted(rows, key=lambda row: order.get(row[0], 999))


def format_consensus(signals: list[tuple[str, dict]]) -> tuple[str, dict[str, int]]:
    counts = {"BULLISH": 0, "NEUTRAL": 0, "BEARISH": 0}
    for _, signal in signals:
        value = str(signal.get("signal", "NEUTRAL")).upper()
        counts[value if value in counts else "NEUTRAL"] += 1
    if counts["BULLISH"] > counts["BEARISH"]:
        overall = "BULLISH"
    elif counts["BEARISH"] > counts["BULLISH"]:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"
    return overall, counts


def format_analyst_grid(signals: list[tuple[str, dict]]) -> list[str]:
    lines = [terminal_section("🧠 ANALYST GRID")]
    lines.extend([
        "  ┌──────────────────────┬───────────┬────────────┬────────┐",
        "  │ Analyst              │ Signal    │ Confidence │ Status │",
        "  ├──────────────────────┼───────────┼────────────┼────────┤",
    ])
    for agent, signal in signals:
        signal_name, colour = status_style(signal.get("signal"))
        marker = _terminal_style(signal_name.split(" ", 1)[0], colour, "bold")
        lines.append(
            f"  │ {_display_name(agent)[:20]:<20} │ "
            f"{str(signal.get('signal', 'NEUTRAL')).upper():<9} │ "
            f"{_confidence(signal.get('confidence')):>8.1f}%  │ {marker:<6} │"
        )
    lines.append("  └──────────────────────┴───────────┴────────────┴────────┘")
    return lines


def format_analyst_detail(agent: str, signal: dict) -> list[str]:
    signal_name, colour = status_style(signal.get("signal"))
    confidence = _confidence(signal.get("confidence"))
    lines = terminal_box(f"📈 {_display_name(agent).upper()}", "INDIVIDUAL RESEARCH OUTPUT")
    lines.extend([
        f"  Signal:       {_terminal_style(signal_name, colour, 'bold')}",
        f"  Confidence:   {confidence:.1f}% {_terminal_style(score_bar(confidence), 'blue')}",
    ])
    if signal.get("reasoning"):
        lines.append(terminal_section("DETAILS"))
        lines.extend(_format_reasoning(signal["reasoning"]))
    return lines


def format_fundamentals(signals: list[tuple[str, dict]]) -> list[str]:
    for agent, signal in signals:
        if "fundamental" in agent.lower() and signal.get("reasoning"):
            lines = terminal_box("💰 FUNDAMENTALS", "ACTUAL RETURNED METRICS ONLY")
            lines.append(terminal_section("FUNDAMENTALS DETAIL"))
            lines.extend(_format_reasoning(signal["reasoning"]))
            return lines
    return []


def format_decision(ticker: str, decision: dict) -> list[str]:
    action = str(decision.get("action", "N/A")).upper()
    colour = "green" if action in {"BUY", "COVER"} else "red" if action in {"SELL", "SHORT"} else "yellow"
    confidence = _confidence(decision.get("confidence"))
    lines = terminal_box("🎯 FUND DECISION", ticker)
    lines.extend([
        f"  ACTION        {_terminal_style(action, colour, 'bold')}",
        f"  QUANTITY      {decision.get('quantity', 'N/A')}",
        f"  CONFIDENCE    {confidence:.1f}% {_terminal_style(score_bar(confidence), 'blue')}",
    ])
    if decision.get("reasoning"):
        lines.append(terminal_section("DECISION RATIONALE"))
        lines.extend(f"  {line}" for line in _wrap(decision["reasoning"]))
    return lines


def format_portfolio(decisions: dict, consensus: dict[str, tuple[str, dict[str, int]]]) -> list[str]:
    lines = terminal_box("📊 PORTFOLIO SUMMARY", "MULTI-TICKER RESEARCH OVERVIEW")
    lines.extend([
        terminal_section("POSITION QUEUE"),
        "  Ticker     Action       Qty       Confidence",
        "  ────────────────────────────────────────────",
    ])
    for ticker, decision in decisions.items():
        lines.append(
            f"  {ticker:<10} {str(decision.get('action', 'N/A')).upper():<12} "
            f"{str(decision.get('quantity', 'N/A')):<9} {_confidence(decision.get('confidence')):>6.1f}%"
        )
    lines.append(terminal_section("CONSENSUS"))
    for ticker, (overall, counts) in consensus.items():
        status, colour = status_style(overall)
        total = sum(counts.values()) or 1
        lines.append(f"  {ticker:<6} {_terminal_style(status, colour, 'bold')}")
        for label in ("BULLISH", "NEUTRAL", "BEARISH"):
            lines.append(f"    {label.title():<9} {_terminal_style(score_bar(counts[label] / total * 100, 10), 'blue')} {counts[label]}")
    return lines


def build_hedge_fund_summary(result: dict) -> str:
    """Build the clean default report while leaving result payloads intact."""
    decisions = result.get("decisions") or {}
    if not decisions:
        return "\n".join(terminal_box("🧠 AI HEDGE FUND", "NO DECISIONS AVAILABLE"))

    lines: list[str] = []
    consensus: dict[str, tuple[str, dict[str, int]]] = {}
    for ticker, decision in decisions.items():
        signals = _signals_for_ticker(result, ticker)
        overall, counts = format_consensus(signals)
        consensus[ticker] = (overall, counts)
        status, colour = status_style(overall)
        confidence = sum(_confidence(signal.get("confidence")) for _, signal in signals) / len(signals) if signals else 0.0
        lines.extend(terminal_box("🧠 AI HEDGE FUND  //  RESEARCH ENGINE", f"{ticker} · MULTI-ANALYST MARKET INTELLIGENCE"))
        lines.extend([
            terminal_section("EXECUTIVE SUMMARY"),
            f"  Ticker:              {ticker}",
            f"  Overall Signal:      {_terminal_style(status, colour, 'bold')}",
            f"  Confidence:          {confidence:.1f}% {_terminal_style(score_bar(confidence), 'blue')}",
            f"  Analysts:            {len(signals)}",
            f"  Bullish:             {counts['BULLISH']}",
            f"  Neutral:             {counts['NEUTRAL']}",
            f"  Bearish:             {counts['BEARISH']}",
            "",
        ])
        total = sum(counts.values()) or 1
        lines.append(terminal_section("CONSENSUS"))
        for label in ("BULLISH", "NEUTRAL", "BEARISH"):
            lines.append(f"  {label.title():<9} {_terminal_style(score_bar(counts[label] / total * 100, 10), 'blue')} {counts[label]}")
        lines.extend(format_analyst_grid(signals))
        fundamentals = format_fundamentals(signals)
        if fundamentals:
            lines.extend(fundamentals)
        for agent, signal in signals:
            lines.extend(format_analyst_detail(agent, signal))
        lines.extend(format_decision(ticker, decision))

    lines.extend(format_portfolio(decisions, consensus))
    lines.extend([
        "",
        _terminal_style("╔" + "═" * TERMINAL_WIDTH + "╗", "blue"),
        _terminal_style("║  🛡  RESEARCH / SIMULATION MODE".ljust(TERMINAL_WIDTH + 1) + "║", "blue"),
        _terminal_style("║  NO AUTOMATIC TRADE EXECUTED".ljust(TERMINAL_WIDTH + 1) + "║", "red", "bold"),
        _terminal_style("║  This application provides research and decision support only.".ljust(TERMINAL_WIDTH + 1) + "║", "muted"),
        _terminal_style("╚" + "═" * TERMINAL_WIDTH + "╝", "blue"),
    ])
    return "\n".join(lines)


def print_trading_output(result: dict) -> None:
    print(build_hedge_fund_summary(result))


def print_backtest_results(table_rows: list) -> None:
    """Print the backtest results in a nicely formatted table"""
    # Clear the screen
    os.system("cls" if os.name == "nt" else "clear")

    # Split rows into ticker rows and summary rows
    ticker_rows = []
    summary_rows = []

    for row in table_rows:
        if isinstance(row[1], str) and "PORTFOLIO SUMMARY" in row[1]:
            summary_rows.append(row)
        else:
            ticker_rows.append(row)

    # Display latest portfolio summary
    if summary_rows:
        # Pick the most recent summary by date (YYYY-MM-DD)
        latest_summary = max(summary_rows, key=lambda r: r[0])
        print(f"\n{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY:{Style.RESET_ALL}")

        # Adjusted indexes after adding Long/Short Shares
        position_str = latest_summary[7].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        cash_str     = latest_summary[8].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        total_str    = latest_summary[9].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")

        print(f"Cash Balance: {Fore.CYAN}${float(cash_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Position Value: {Fore.YELLOW}${float(position_str):,.2f}{Style.RESET_ALL}")
        print(f"Total Value: {Fore.WHITE}${float(total_str):,.2f}{Style.RESET_ALL}")
        print(f"Portfolio Return: {latest_summary[10]}")
        if len(latest_summary) > 14 and latest_summary[14]:
            print(f"Benchmark Return: {latest_summary[14]}")

        # Display performance metrics if available
        if latest_summary[11]:  # Sharpe ratio
            print(f"Sharpe Ratio: {latest_summary[11]}")
        if latest_summary[12]:  # Sortino ratio
            print(f"Sortino Ratio: {latest_summary[12]}")
        if latest_summary[13]:  # Max drawdown
            print(f"Max Drawdown: {latest_summary[13]}")

    # Add vertical spacing
    print("\n" * 2)

    # Print the table with just ticker rows
    print(
        tabulate(
            ticker_rows,
            headers=[
                "Date",
                "Ticker",
                "Action",
                "Quantity",
                "Price",
                "Long Shares",
                "Short Shares",
                "Position Value",
            ],
            tablefmt="grid",
            colalign=(
                "left",    # Date
                "left",    # Ticker
                "center",  # Action
                "right",   # Quantity
                "right",   # Price
                "right",   # Long Shares
                "right",   # Short Shares
                "right",   # Position Value
            ),
        )
    )

    # Add vertical spacing
    print("\n" * 4)


def format_backtest_row(
    date: str,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    long_shares: float = 0,
    short_shares: float = 0,
    position_value: float = 0,
    is_summary: bool = False,
    total_value: float = None,
    return_pct: float = None,
    cash_balance: float = None,
    total_position_value: float = None,
    sharpe_ratio: float = None,
    sortino_ratio: float = None,
    max_drawdown: float = None,
    benchmark_return_pct: float | None = None,
) -> list[any]:
    """Format a row for the backtest results table"""
    # Color the action
    action_color = {
        "BUY": Fore.GREEN,
        "COVER": Fore.GREEN,
        "SELL": Fore.RED,
        "SHORT": Fore.RED,
        "HOLD": Fore.WHITE,
    }.get(action.upper(), Fore.WHITE)

    if is_summary:
        return_color = Fore.GREEN if return_pct >= 0 else Fore.RED
        benchmark_str = ""
        if benchmark_return_pct is not None:
            bench_color = Fore.GREEN if benchmark_return_pct >= 0 else Fore.RED
            benchmark_str = f"{bench_color}{benchmark_return_pct:+.2f}%{Style.RESET_ALL}"
        return [
            date,
            f"{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY{Style.RESET_ALL}",
            "",  # Action
            "",  # Quantity
            "",  # Price
            "",  # Long Shares
            "",  # Short Shares
            f"{Fore.YELLOW}${total_position_value:,.2f}{Style.RESET_ALL}",  # Total Position Value
            f"{Fore.CYAN}${cash_balance:,.2f}{Style.RESET_ALL}",  # Cash Balance
            f"{Fore.WHITE}${total_value:,.2f}{Style.RESET_ALL}",  # Total Value
            f"{return_color}{return_pct:+.2f}%{Style.RESET_ALL}",  # Return
            f"{Fore.YELLOW}{sharpe_ratio:.2f}{Style.RESET_ALL}" if sharpe_ratio is not None else "",  # Sharpe Ratio
            f"{Fore.YELLOW}{sortino_ratio:.2f}{Style.RESET_ALL}" if sortino_ratio is not None else "",  # Sortino Ratio
            f"{Fore.RED}{max_drawdown:.2f}%{Style.RESET_ALL}" if max_drawdown is not None else "",  # Max Drawdown (signed)
            benchmark_str,  # Benchmark (S&P 500)
        ]
    else:
        return [
            date,
            f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
            f"{action_color}{action.upper()}{Style.RESET_ALL}",
            f"{action_color}{quantity:,.0f}{Style.RESET_ALL}",
            f"{Fore.WHITE}{price:,.2f}{Style.RESET_ALL}",
            f"{Fore.GREEN}{long_shares:,.0f}{Style.RESET_ALL}",   # Long Shares
            f"{Fore.RED}{short_shares:,.0f}{Style.RESET_ALL}",    # Short Shares
            f"{Fore.YELLOW}{position_value:,.2f}{Style.RESET_ALL}",
        ]
