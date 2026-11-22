import datetime
import logging
import os
import pandas as pd
import requests
import threading
import time
import yfinance as yf

logger = logging.getLogger(__name__)

# Yahoo statements are reused by several analysts in one run. Cache the raw
# frames briefly so the fallback does not refetch the same statements 10x.
_STATEMENT_CACHE: dict[str, tuple[float, dict]] = {}
_STATEMENT_LOCK = threading.Lock()
_STATEMENT_TTL = 600.0

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    Price,
    PriceResponse,
    LineItem,
    LineItemResponse,
    InsiderTrade,
    InsiderTradeResponse,
    CompanyFactsResponse,
)

# Global cache instance
_cache = get_cache()


def _make_api_request(url: str, headers: dict, method: str = "GET", json_data: dict = None, max_retries: int = 3) -> requests.Response:
    """
    Make an API request with rate limiting handling and moderate backoff.
    
    Args:
        url: The URL to request
        headers: Headers to include in the request
        method: HTTP method (GET or POST)
        json_data: JSON data for POST requests
        max_retries: Maximum number of retries (default: 3)
    
    Returns:
        requests.Response: The response object
    
    Raises:
        Exception: If the request fails with a non-429 error
    """
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data)
        else:
            response = requests.get(url, headers=headers)
        
        if response.status_code == 429 and attempt < max_retries:
            # Linear backoff: 60s, 90s, 120s, 150s...
            delay = 60 + (30 * attempt)
            print(f"Rate limited (429). Attempt {attempt + 1}/{max_retries + 1}. Waiting {delay}s before retrying...")
            time.sleep(delay)
            continue
        
        # Return the response (whether success, other errors, or final 429)
        return response


def get_prices(ticker: str, start_date: str, end_date: str, api_key: str = None) -> list[Price]:
    """Fetch price data from Yahoo Finance."""

    # Check the cache first (simple ticker key; the cache merges by time)
    cached = _cache.get_prices(ticker)
    if cached is not None:
        return [Price(**p) for p in cached]

    try:
        stock = yf.Ticker(ticker)

        df = stock.history(
            start=start_date,
            end=end_date
        )

        if df.empty:
            return []

        prices = []

        for index, row in df.iterrows():
            prices.append(
                Price(
                    time=index.isoformat(),
                    open=float(row["Open"]),
                    close=float(row["Close"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    volume=int(row["Volume"])
                )
            )

        _cache.set_prices(ticker, [p.model_dump() for p in prices])
        return prices

    except Exception as e:
        logger.warning("Yahoo price fetch failed for %s: %s", ticker, e)
        return []


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    """Fetch financial metrics from Yahoo Finance (free, no API key required)."""

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Yahoo reports debt/equity as a percentage (16.971 = 16.971%),
        # while the analyst models expect a ratio (0.16971).
        debt_raw = info.get("debtToEquity")
        try:
            debt_to_equity = float(debt_raw) / 100.0 if debt_raw is not None else None
        except (TypeError, ValueError):
            debt_to_equity = None

        metrics = FinancialMetrics(
            ticker=ticker,
            report_period=end_date,
            period=period,
            currency="USD",

            # Valuation
            market_cap=info.get("marketCap"),
            enterprise_value=info.get("enterpriseValue"),
            
            earnings_per_share=info.get("trailingEps"),
            book_value_per_share=info.get("bookValue"),
            free_cash_flow_per_share=None,

            price_to_earnings_ratio=info.get("trailingPE"),
            price_to_book_ratio=info.get("priceToBook"),
            price_to_sales_ratio=info.get("priceToSalesTrailing12Months"),
            enterprise_value_to_ebitda_ratio=info.get("enterpriseToEbitda"),
            enterprise_value_to_revenue_ratio=info.get("enterpriseToRevenue"),
            peg_ratio=info.get("pegRatio"),

            # Profitability
            gross_margin=info.get("grossMargins"),
            operating_margin=info.get("operatingMargins"),
            net_margin=info.get("profitMargins"),

            return_on_equity=info.get("returnOnEquity"),
            return_on_assets=info.get("returnOnAssets"),
            return_on_invested_capital=None,

            # Efficiency
            asset_turnover=None,
            inventory_turnover=None,
            receivables_turnover=None,
            days_sales_outstanding=None,
            operating_cycle=None,
            working_capital_turnover=None,

            # Liquidity
            current_ratio=info.get("currentRatio"),
            quick_ratio=info.get("quickRatio"),
            cash_ratio=None,
            operating_cash_flow_ratio=None,

            # Debt
            debt_to_equity=debt_to_equity,
            debt_to_assets=None,
            interest_coverage=None,

            # Growth
            revenue_growth=info.get("revenueGrowth"),
            earnings_growth=info.get("earningsGrowth"),
            book_value_growth=None,
            earnings_per_share_growth=None,
            free_cash_flow_growth=None,
            operating_income_growth=None,
            ebitda_growth=None,

            # Cash flow
            free_cash_flow_yield=None,

            # Dividends
            payout_ratio=info.get("payoutRatio"),
        )

        # Fill growth fields that Yahoo exposes only in the statements, not
        # in the quote summary. Calculations are current-vs-year-ago quarter.
        try:
            growth = _yahoo_growth_rates(ticker, end_date)
            for field, value in growth.items():
                if value is not None and getattr(metrics, field, None) is None:
                    setattr(metrics, field, value)
        except Exception as exc:
            logger.debug("Yahoo growth history unavailable for %s: %s", ticker, exc)

        return [metrics]

    except Exception as e:
        logger.warning(
            "Yahoo financial metrics failed for %s: %s",
            ticker,
            e
        )
        return []


def _number(value) -> float | None:
    """Convert a statement cell to a clean float, preserving None."""
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _statement_value(frame: pd.DataFrame | None, labels: tuple[str, ...], column) -> float | None:
    """Read the first matching row from a Yahoo statement column."""
    if frame is None or frame.empty:
        return None
    for label in labels:
        if label not in frame.index:
            continue
        try:
            row = frame.loc[label]
            if getattr(row, "ndim", 1) > 1:
                row = row.iloc[0]
            value = _number(row.get(column))
        except (KeyError, IndexError, TypeError):
            continue
        if value is not None:
            return value
    return None


def _statement_sum(frame: pd.DataFrame | None, labels: tuple[str, ...], column) -> float | None:
    values = [_statement_value(frame, (label,), column) for label in labels]
    known = [value for value in values if value is not None]
    return sum(known) if known else None


def _yahoo_statements(ticker: str, end_date: str) -> dict:
    """Load quarterly statements once per ticker for the Yahoo fallback."""
    key = f"{ticker.upper()}:{end_date}"
    now = time.time()
    with _STATEMENT_LOCK:
        cached = _STATEMENT_CACHE.get(key)
        if cached and now - cached[0] < _STATEMENT_TTL:
            return cached[1]

    stock = yf.Ticker(ticker)
    try:
        info = stock.info or {}
    except Exception:
        info = {}
    payload = {
        "financials": stock.quarterly_financials,
        "balance": stock.quarterly_balance_sheet,
        "cashflow": stock.quarterly_cashflow,
        "currency": str(info.get("currency") or "USD"),
    }
    with _STATEMENT_LOCK:
        _STATEMENT_CACHE[key] = (now, payload)
    return payload


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return current / previous - 1.0


def _yahoo_growth_rates(ticker: str, end_date: str) -> dict[str, float | None]:
    """Compute year-over-year growth from the cached Yahoo statements."""
    statements = _yahoo_statements(ticker, end_date)
    financials = statements["financials"]
    cashflow = statements["cashflow"]
    balance = statements["balance"]
    if financials is None or financials.empty:
        return {}

    # Respect the requested as-of date. Backtests must not see a later
    # quarter just because Yahoo currently has newer statements.
    columns = sorted(
        (column for column in financials.columns if str(column)[:10] <= str(end_date)[:10]),
        key=lambda value: str(value),
        reverse=True,
    )
    if len(columns) < 5:
        return {}
    current = columns[0]
    prior = columns[4]

    def series_value(frame, labels, column):
        return _statement_value(frame, labels, column)

    revenue = _growth(
        series_value(financials, ("Total Revenue", "Operating Revenue"), current),
        series_value(financials, ("Total Revenue", "Operating Revenue"), prior),
    )
    net_income = _growth(
        series_value(financials, ("Net Income Common Stockholders", "Net Income"), current),
        series_value(financials, ("Net Income Common Stockholders", "Net Income"), prior),
    )
    eps = _growth(
        series_value(financials, ("Diluted EPS", "Basic EPS"), current),
        series_value(financials, ("Diluted EPS", "Basic EPS"), prior),
    )
    operating_income = _growth(
        series_value(financials, ("Operating Income", "EBIT"), current),
        series_value(financials, ("Operating Income", "EBIT"), prior),
    )
    ebitda = _growth(
        series_value(financials, ("EBITDA", "Normalized EBITDA"), current),
        series_value(financials, ("EBITDA", "Normalized EBITDA"), prior),
    )

    def fcf(frame, column):
        direct = series_value(frame, ("Free Cash Flow",), column)
        if direct is not None:
            return direct
        operating = series_value(frame, ("Operating Cash Flow",), column)
        capex = series_value(frame, ("Capital Expenditure", "Purchase Of PPE"), column)
        if operating is None or capex is None:
            return None
        return operating - abs(capex)

    free_cash_flow = _growth(fcf(cashflow, current), fcf(cashflow, prior))
    equity = _growth(
        series_value(balance, ("Stockholders Equity", "Common Stock Equity"), current),
        series_value(balance, ("Stockholders Equity", "Common Stock Equity"), prior),
    )
    return {
        "revenue_growth": revenue,
        "earnings_growth": net_income,
        "earnings_per_share_growth": eps,
        "free_cash_flow_growth": free_cash_flow,
        "operating_income_growth": operating_income,
        "ebitda_growth": ebitda,
        "book_value_growth": equity,
    }


def _yahoo_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str,
    limit: int,
) -> list[LineItem]:
    """Build financial line items from Yahoo quarterly statements.

    This is the no-key fallback for the paid Financial Datasets endpoint.
    Values are only emitted when Yahoo actually reports them; nothing is
    estimated or fabricated.
    """
    try:
        statements = _yahoo_statements(ticker, end_date)
    except Exception as exc:
        logger.warning("Yahoo statement fallback failed for %s: %s", ticker, exc)
        return []

    financials = statements["financials"]
    balance = statements["balance"]
    cashflow = statements["cashflow"]
    currency = statements["currency"]

    frames = [frame for frame in (financials, balance, cashflow) if frame is not None and not frame.empty]
    if not frames:
        return []

    columns: list = []
    seen: set[str] = set()
    for frame in frames:
        for column in frame.columns:
            stamp = str(column)[:10]
            if stamp and stamp not in seen and stamp <= str(end_date)[:10]:
                seen.add(stamp)
                columns.append(column)
    columns.sort(key=lambda value: str(value), reverse=True)

    rows: list[LineItem] = []
    for column in columns[: max(1, min(limit, 12))]:
        revenue = _statement_value(financials, ("Total Revenue", "Operating Revenue"), column)
        net_income = _statement_value(financials, ("Net Income Common Stockholders", "Net Income"), column)
        operating_income = _statement_value(financials, ("Operating Income", "EBIT"), column)
        ebit = _statement_value(financials, ("EBIT", "Operating Income"), column)
        interest = _statement_value(financials, ("Interest Expense", "Interest Expense Non Operating"), column)
        depreciation = _statement_value(
            cashflow,
            ("Depreciation And Amortization", "Depreciation Amortization Depletion", "Depreciation"),
            column,
        )
        if depreciation is None:
            depreciation = _statement_value(financials, ("Reconciled Depreciation", "Depreciation"), column)

        capex = _statement_value(cashflow, ("Capital Expenditure", "Purchase Of PPE"), column)
        capex = abs(capex) if capex is not None else None
        operating_cash = _statement_value(cashflow, ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"), column)
        free_cash_flow = _statement_value(cashflow, ("Free Cash Flow",), column)
        if free_cash_flow is None and operating_cash is not None and capex is not None:
            free_cash_flow = operating_cash - capex

        ebitda = _statement_value(financials, ("EBITDA", "Normalized EBITDA"), column)
        if ebitda is None and ebit is not None and depreciation is not None:
            ebitda = ebit + depreciation

        current_assets = _statement_value(balance, ("Current Assets",), column)
        current_liabilities = _statement_value(balance, ("Current Liabilities",), column)
        working_capital = _statement_value(balance, ("Working Capital",), column)
        if working_capital is None and current_assets is not None and current_liabilities is not None:
            working_capital = current_assets - current_liabilities

        total_debt = _statement_value(balance, ("Total Debt",), column)
        if total_debt is None:
            total_debt = _statement_sum(balance, ("Long Term Debt", "Current Debt", "Current Debt And Capital Lease Obligation"), column)
        cash = _statement_value(
            balance,
            ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"),
            column,
        )
        total_assets = _statement_value(balance, ("Total Assets",), column)
        total_liabilities = _statement_value(balance, ("Total Liabilities Net Minority Interest", "Total Liabilities"), column)
        equity = _statement_value(balance, ("Stockholders Equity", "Common Stock Equity"), column)
        shares = _statement_value(balance, ("Ordinary Shares Number", "Share Issued"), column)
        invested_capital = _statement_value(balance, ("Invested Capital",), column)
        if invested_capital is None and total_assets is not None and current_liabilities is not None:
            invested_capital = total_assets - current_liabilities

        gross_profit = _statement_value(financials, ("Gross Profit",), column)
        operating_expense = _statement_value(financials, ("Operating Expense", "Total Expenses"), column)
        research_and_development = _statement_value(financials, ("Research And Development",), column)
        goodwill = _statement_value(balance, ("Goodwill And Other Intangible Assets", "Goodwill", "Other Intangible Assets"), column)
        eps = _statement_value(financials, ("Diluted EPS", "Basic EPS"), column)
        dividends = _statement_value(cashflow, ("Cash Dividends Paid", "Common Stock Dividend Paid"), column)
        issuance = _statement_value(cashflow, ("Net Common Stock Issuance",), column)
        if issuance is None:
            issuance = _statement_sum(
                cashflow,
                ("Repurchase Of Capital Stock", "Common Stock Payments", "Proceeds From Stock Option Exercised"),
                column,
            )

        gross_margin = gross_profit / revenue if gross_profit is not None and revenue else None
        operating_margin = operating_income / revenue if operating_income is not None and revenue else None
        debt_to_equity = total_debt / equity if total_debt is not None and equity else None
        book_value_per_share = equity / shares if equity is not None and shares else None
        roic = 0.75 * ebit / invested_capital if ebit is not None and invested_capital else None

        values = {
            "free_cash_flow": free_cash_flow,
            "net_income": net_income,
            "depreciation_and_amortization": depreciation,
            "capital_expenditure": capex,
            "working_capital": working_capital,
            "total_debt": total_debt,
            "cash_and_equivalents": cash,
            "interest_expense": abs(interest) if interest is not None else None,
            "revenue": revenue,
            "operating_income": operating_income,
            "ebit": ebit,
            "ebitda": ebitda,
            "earnings_per_share": eps,
            "book_value_per_share": book_value_per_share,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "current_assets": current_assets,
            "current_liabilities": current_liabilities,
            "shareholders_equity": equity,
            "outstanding_shares": shares,
            "gross_profit": gross_profit,
            "operating_expense": operating_expense,
            "research_and_development": research_and_development,
            "goodwill_and_intangible_assets": goodwill,
            "dividends_and_other_cash_distributions": dividends,
            "issuance_or_purchase_of_equity_shares": issuance,
            "gross_margin": gross_margin,
            "operating_margin": operating_margin,
            "debt_to_equity": debt_to_equity,
            "return_on_invested_capital": roic,
        }
        if not any(value is not None for value in values.values()):
            continue

        # Keep every requested key present even when Yahoo lacks it. Agents
        # access attributes directly; a missing attribute used to raise and
        # surface as an "Engine error" card in the GUI.
        all_values = {name: None for name in line_items}
        all_values.update(values)
        rows.append(
            LineItem(
                ticker=ticker,
                report_period=str(column)[:10],
                period=period,
                currency=currency,
                **all_values,
            )
        )
    return rows


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    """Fetch line items, falling back to Yahoo statements without a paid key."""
    headers = {}
    financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")

    # The Yahoo fallback is the intended path for free local runs. Do not waste
    # a request on the paid endpoint when no key is configured.
    if not financial_api_key:
        return _yahoo_line_items(ticker, line_items, end_date, period, limit)

    headers["X-API-KEY"] = financial_api_key
    url = "https://api.financialdatasets.ai/financials/search/line-items"
    body = {
        "tickers": [ticker],
        "line_items": line_items,
        "end_date": end_date,
        "period": period,
        "limit": limit,
    }
    response = _make_api_request(url, headers, method="POST", json_data=body)
    if response.status_code == 200:
        try:
            data = response.json()
            response_model = LineItemResponse(**data)
            search_results = response_model.search_results
            if search_results:
                return search_results[:limit]
        except Exception as e:
            logger.warning("Failed to parse line items response for %s: %s", ticker, e)

    # Paid endpoint unavailable or empty: still give analysts real data.
    return _yahoo_line_items(ticker, line_items, end_date, period, limit)


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    """Fetch insider trades from cache or API."""
    # Create a cache key that includes all parameters to ensure exact matches
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    
    # Check cache first - simple exact match
    if cached_data := _cache.get_insider_trades(cache_key):
        return [InsiderTrade(**trade) for trade in cached_data]

    # If not in cache, fetch from API
    headers = {}
    financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
    if financial_api_key:
        headers["X-API-KEY"] = financial_api_key

    all_trades = []
    current_end_date = end_date

    while True:
        url = f"https://api.financialdatasets.ai/insider-trades/?ticker={ticker}&filing_date_lte={current_end_date}"
        if start_date:
            url += f"&filing_date_gte={start_date}"
        url += f"&limit={limit}"

        response = _make_api_request(url, headers)
        if response.status_code != 200:
            break

        try:
            data = response.json()
            response_model = InsiderTradeResponse(**data)
            insider_trades = response_model.insider_trades
        except Exception as e:
            logger.warning("Failed to parse insider trades response for %s: %s", ticker, e)
            break

        if not insider_trades:
            break

        all_trades.extend(insider_trades)

        # Only continue pagination if we have a start_date and got a full page
        if not start_date or len(insider_trades) < limit:
            break

        # Update end_date to the oldest filing date from current batch for next iteration
        current_end_date = min(trade.filing_date for trade in insider_trades).split("T")[0]

        # If we've reached or passed the start_date, we can stop
        if current_end_date <= start_date:
            break

    if not all_trades:
        return []

    # Cache the results using the comprehensive cache key
    _cache.set_insider_trades(cache_key, [trade.model_dump() for trade in all_trades])
    return all_trades


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    """Fetch company news from cache or API."""
    # Create a cache key that includes all parameters to ensure exact matches
    cache_key = f"{ticker}_{start_date or 'none'}_{end_date}_{limit}"
    
    # Check cache first - simple exact match
    if cached_data := _cache.get_company_news(cache_key):
        return [CompanyNews(**news) for news in cached_data]

    # If not in cache, fetch from API
    headers = {}
    financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
    if financial_api_key:
        headers["X-API-KEY"] = financial_api_key

    all_news = []
    current_end_date = end_date

    while True:
        url = f"https://api.financialdatasets.ai/news/?ticker={ticker}&end_date={current_end_date}"
        if start_date:
            url += f"&start_date={start_date}"
        url += f"&limit={limit}"

        response = _make_api_request(url, headers)
        if response.status_code != 200:
            break

        try:
            data = response.json()
            response_model = CompanyNewsResponse(**data)
            company_news = response_model.news
        except Exception as e:
            logger.warning("Failed to parse company news response for %s: %s", ticker, e)
            break

        if not company_news:
            break

        all_news.extend(company_news)

        # Only continue pagination if we have a start_date and got a full page
        if not start_date or len(company_news) < limit:
            break

        # Update end_date to the oldest date from current batch for next iteration
        current_end_date = min(news.date for news in company_news).split("T")[0]

        # If we've reached or passed the start_date, we can stop
        if current_end_date <= start_date:
            break

    if not all_news:
        return []

    # Cache the results using the comprehensive cache key
    _cache.set_company_news(cache_key, [news.model_dump() for news in all_news])
    return all_news


def get_market_cap(
    ticker: str,
    end_date: str,
    api_key: str = None,
) -> float | None:
    """Fetch market cap from Yahoo Finance."""

    try:
        stock = yf.Ticker(ticker)

        info = stock.info

        return info.get("marketCap")

    except Exception as e:
        logger.warning("Yahoo market cap failed for %s: %s", ticker, e)
        return None


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    df["Date"] = pd.to_datetime(df["time"])
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


# Update the get_price_data function to use the new functions
def get_price_data(ticker: str, start_date: str, end_date: str, api_key: str = None) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date, api_key=api_key)
    return prices_to_df(prices)
