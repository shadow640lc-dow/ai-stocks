# AI Hedge Fund Development Manual

## Project Overview

Project name:

**AI Stocks / AI Hedge Fund**

Repository:

`https://github.com/shadow640lc-dow/ai-stocks`

Original project:

Forked from:

`virattt/ai-hedge-fund`

Goal:

Build a personal AI-powered stock analysis platform using:

* Multiple AI investment analysts
* Local LLMs
* Market data
* Backtesting
* Historical performance tracking
* Portfolio reports
* Automated daily analysis

---

# 1. GitHub Fork Migration

## Original Repository

The project started from:

```
virattt/ai-hedge-fund
```

A personal fork was created:

```
shadow640lc-dow/ai-stocks
```

## Local Repository Setup

Clone location:

```
~/ai-hedge-fund
```

Check remote:

```bash
git remote -v
```

Result:

```
origin https://github.com/shadow640lc-dow/ai-stocks.git
```

---

# 2. GitHub Authentication Setup

Problem:

Git push failed:

```
Password authentication is not supported for Git operations
```

Solution:

Installed GitHub CLI:

```bash
sudo apt install gh
```

Authenticated:

```bash
gh auth login
```

Login method:

```
GitHub.com
HTTPS
Browser authentication
```

Verify:

```bash
gh auth status
```

Successful result:

```
Logged in to github.com account shadow640lc-dow
Git operations protocol: https
Token scopes:
repo
workflow
```

---

# 3. First Project Release

Created project manual:

```
AI_HEDGE_FUND_MANUAL.md
```

Committed:

```bash
git add AI_HEDGE_FUND_MANUAL.md

git commit -m "Add AI hedge fund setup and migration manual"
```

Pushed:

```bash
git push
```

Created first milestone:

```bash
git tag -a v1.0-yfinance \
-m "AI Stocks v1.0 - Yahoo Finance migration"
```

Push tag:

```bash
git push origin v1.0-yfinance
```

Release:

```
v1.0-yfinance
```

Meaning:

* Yahoo Finance market data working
* Fork migrated
* Documentation started

---

# 4. Current AI Analysis Engine

The project currently supports multiple AI analyst roles.

Enabled analysts:

* Warren Buffett
* Charlie Munger
* Cathie Wood
* Bill Ackman
* Technical Analyst
* Fundamentals Analyst
* Growth Analyst
* Sentiment Analyst
* News Sentiment Analyst
* Valuation Analyst
* Risk Management
* Portfolio Manager

Example command:

```bash
poetry run python src/main.py --ticker NVDA
```

Example output:

```
Analysis for NVDA

Technical Analyst
Fundamentals Analyst
Sentiment Analyst
Warren Buffett

Trading Decision:

BUY
Confidence: 50%
Quantity: 68
```

---

# 5. Initial Cloud LLM Support

Originally the project used:

## xAI Grok

Configuration:

```
src/llm/api_models.json
```

Example:

```json
{
"display_name":"Grok 4.3",
"model_name":"grok-4.3",
"provider":"xAI"
}
```

The API worked after adding:

```
xAI API key
```

The project successfully generated reports using:

```
Grok 4.3
```

---

# 6. Added Local AI Support

Goal:

Reduce API costs and run AI locally.

Installed locally:

* Ollama
* Qwen3

Existing local models:

```bash
ollama list
```

Current local AI:

```
qwen3:8b
```

---

# 7. Ollama Integration

The project already had:

```
langchain-ollama
```

Verified:

```bash
poetry add langchain-ollama
```

Result:

```
already present
```

---

# 8. Updated Model Configuration

Original:

```
src/llm/ollama_models.json
```

Problem:

Models had incorrect providers:

Before:

```json
{
"provider":"Alibaba"
}
```

Changed to:

```json
{
"provider":"Ollama"
}
```

Reason:

The AI Hedge Fund model selector uses provider matching.

---

# 9. Added Ollama Models

Available local models:

```json
Qwen 3 (4B)
Qwen 3 (8B)
Qwen 3 (30B-a3B)
Gemma
Llama
Mistral
GPT OSS
```

Example:

```json
{
"display_name":"Qwen 3 (8B)",
"model_name":"qwen3:8b",
"provider":"Ollama"
}
```

---

# 10. Fixed Model Loading

Updated:

```
src/llm/models.py
```

Added Ollama models into the selection flow.

Before:

Only:

```
api_models.json
```

After:

```
api_models.json
+
ollama_models.json
```

---

# 11. Testing Local AI

Command:

```bash
poetry run python src/main.py --ticker NVDA
```

Selected:

```
Qwen 3 (8B)
```

Result:

```
Selected Ollama model: qwen3:8b
```

Successful:

```
Fundamentals Analyst Done
Growth Analyst Done
Sentiment Analyst Done
Technical Analyst Done
Portfolio Manager Done
Risk Management Done
```

---

# 12. Failed Model Test

Attempted:

```
Qwen 3 (30B-a3B)
```

Error:

```
model 'qwen3:30b-a3b' not found
```

Reason:

Model exists in configuration but is not installed in Ollama.

Check:

```bash
ollama list
```

Install if desired:

```bash
ollama pull qwen3:30b-a3b
```

---

# 13. Current Working Architecture

```
AI Hedge Fund

        |
        |
        v

Market Data
(Yahoo Finance)

        |
        |
        v

AI Analysts

        |
        |
        +---- Grok API
        |
        +---- Ollama Local Models
              |
              +-- Qwen3


        |
        |
        v

Portfolio Manager

        |
        |
        v

Trading Decision

BUY / HOLD / SELL
```

---

# 14. Next Development Roadmap

## Phase 1 - Complete Local AI

Add:

* Qwen3
* Mistral
* DeepSeek
* Local model switching

Tasks:

* Install models
* Test accuracy
* Compare against Grok

---

# Phase 2 - Database Layer

Add:

PostgreSQL or SQLite

Store:

* Daily stock analysis
* AI decisions
* Confidence scores
* Portfolio history
* Model performance

Example:

```
database/

stocks
|
|-- ticker
|-- date
|-- price
|-- decision
|-- confidence
|-- reasoning
```

---

# Phase 3 - Backtesting Engine

Purpose:

Test:

"Would this AI strategy have made money historically?"

Features:

* Historical prices
* Previous AI decisions
* Profit/loss simulation
* Win rate
* Maximum drawdown
* Sharpe ratio

---

# Phase 4 - Dashboard

Options:

## Streamlit

Simple:

```
Python dashboard
```

or

## FastAPI + React

Advanced:

```
Backend API
+
Web dashboard
```

Dashboard features:

* Current portfolio
* AI signals
* Historical charts
* Model comparison

---

# Phase 5 - Automated Runs

Create scheduled jobs.

Example:

Every market close:

```
4:30 PM EST

Run AI analysis

Save database

Generate report

Email/dashboard update
```

Possible tools:

* Cron
* Celery
* Airflow

---

# Current Version

## AI Stocks v1.1

Completed:

✅ Forked GitHub repository
✅ GitHub authentication
✅ Project documentation
✅ Yahoo Finance migration
✅ AI analyst framework
✅ Grok API support
✅ Ollama integration
✅ Qwen3 local model support
✅ Local AI analysis working
✅ Git tags/releases

Next milestone:

## AI Stocks v2.0

Goals:

* Database
* Backtesting
* Dashboard
* Automated portfolio reports
* Multi-model AI comparison

---

# Development Notes

Always commit after major changes:

```bash
git add .

git commit -m "description"

git push
```

Create version tags:

```bash
git tag -a vx.x -m "release notes"

git push origin vx.x
```
