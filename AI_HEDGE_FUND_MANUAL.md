# AI Hedge Fund Fork & Free Data Migration Manual

## Project Overview

This document explains how we forked the original AI Hedge Fund project, created our own GitHub repository, replaced paid financial data dependencies with free Yahoo Finance data, and pushed our customized version.

Original project:

* Source: `virattt/ai-hedge-fund`

Custom fork:

* Repository: `shadow640lc-dow/ai-stocks`

---

# 1. Clone / Enter the Project

Navigate to the project directory:

```bash
cd ~/ai-hedge-fund
```

Verify the repository:

```bash
git status
```

Expected:

```text
On branch main
```

---

# 2. Create a Personal Fork

The project was forked from the original GitHub repository.

Original:

```text
https://github.com/virattt/ai-hedge-fund
```

New personal repository:

```text
https://github.com/shadow640lc-dow/ai-stocks
```

The fork allows independent modifications without changing the original project.

---

# 3. Change Git Remote to Personal Fork

Check current remote:

```bash
git remote -v
```

Original:

```text
origin https://github.com/virattt/ai-hedge-fund.git
```

Change it to the personal fork:

```bash
git remote set-url origin https://github.com/shadow640lc-dow/ai-stocks.git
```

Verify:

```bash
git remote -v
```

Expected:

```text
origin https://github.com/shadow640lc-dow/ai-stocks.git
```

---

# 4. Configure Git Identity

Git required a username and email before creating commits.

Configure:

```bash
git config --global user.email "your-email@example.com"
git config --global user.name "your-github-username"
```

Verify:

```bash
git config --global --list
```

---

# 5. Replace Paid Financial Data API

## Problem

The original project depended on:

```text
Financial Datasets API
```

The API required credits and returned:

```json
{
 "error":"Insufficient credits",
 "message":"Your current balance is $0.00"
}
```

Because of this, the project could not run fully without payment.

---

# 6. Add Yahoo Finance Support

Yahoo Finance was chosen as a free replacement.

Python package:

```bash
yfinance
```

Installed with Poetry:

```bash
poetry add yfinance
```

This updated:

```text
pyproject.toml
poetry.lock
```

---

# 7. Modify Financial Metrics

File changed:

```text
src/tools/api.py
```

The function:

```python
get_financial_metrics()
```

was modified to use Yahoo Finance.

The replacement provides:

* Market capitalization
* P/E ratio
* Price-to-book ratio
* Price-to-sales ratio
* EV/EBITDA
* Revenue growth
* Earnings growth
* ROE
* Margins
* Debt ratios
* Liquidity ratios
* Earnings per share

Example test:

```python
from src.tools.api import get_financial_metrics

data = get_financial_metrics("NVDA", "2026-07-08")

print(data[0])
```

Successful output:

```text
ticker='NVDA'
market_cap=4943990226944.0
price_to_earnings_ratio=31.211008
gross_margin=0.74144995
net_margin=0.62966
earnings_per_share=6.54
```

---

# 8. Commit Changes

Check modified files:

```bash
git status
```

Add changes:

```bash
git add src/tools/api.py
```

Commit:

```bash
git commit -m "Replace financial metrics API with Yahoo Finance"
```

---

# 9. Add Dependency Commit

Add dependency files:

```bash
git add pyproject.toml poetry.lock
```

Commit:

```bash
git commit -m "Add yfinance dependency"
```

---

# 10. Install GitHub CLI

Git authentication failed initially because GitHub removed password authentication.

Install GitHub CLI:

```bash
sudo apt update
sudo apt install gh
```

Verify:

```bash
gh --version
```

---

# 11. Authenticate GitHub

Login:

```bash
gh auth login
```

Choose:

```text
GitHub.com
HTTPS
Login with web browser
```

Verify:

```bash
gh auth status
```

Successful output:

```text
Logged in to github.com account shadow640lc-dow
```

---

# 12. Push Changes

Push commits:

```bash
git push -u origin main
```

Successful result:

```text
main -> main
branch 'main' set up to track 'origin/main'
```

---

# 13. Running the AI Hedge Fund

Launch:

```bash
poetry run python src/main.py --ticker AAPL,MSFT,NVDA
```

Select analysts:

Example:

```text
Warren Buffett
Technical Analyst
Fundamentals Analyst
Growth Analyst
News Sentiment Analyst
Sentiment Analyst
Valuation Analyst
```

Select model:

Example:

```text
Grok 4.3
```

The system will run:

* Fundamentals analysis
* Growth analysis
* Technical analysis
* Sentiment analysis
* Valuation analysis
* Risk management
* Portfolio decision

---

# 14. Current Improvements

Completed:

✅ Personal GitHub fork created
✅ Git remote changed
✅ Git authentication configured
✅ Paid financial metrics API removed
✅ Yahoo Finance integration added
✅ Poetry dependencies updated
✅ Changes pushed to GitHub

---

# 15. Future Free API Replacements

Remaining paid dependencies can be replaced:

## Stock Prices

Replace:

```python
get_prices()
```

with:

```python
yfinance.download()
```

---

## News

Replace:

```python
get_company_news()
```

with:

* Yahoo Finance news
* RSS feeds
* SEC filings
* Free news APIs

---

## Insider Trading

Replace:

```python
get_insider_trades()
```

with:

* SEC EDGAR API

---

## Financial Statements

Replace:

```python
search_line_items()
```

with:

Yahoo Finance:

```python
ticker.financials
ticker.balance_sheet
ticker.cashflow
```

---

# Final Project Status

The AI Hedge Fund has been converted from a paid API-dependent project into a free-data version using Yahoo Finance.

Current repository:

```text
shadow640lc-dow/ai-stocks
```

Current branch:

```text
main
```

Status:

```text
Working AI stock analysis system using free financial data
```
