# AI Hedge Fund Development Manual v3

## Project Overview

Project: AI Hedge Fund
Location:

~/ai-hedge-fund

Purpose:

A multi-agent AI stock analysis system using:
- LangChain
- Local LLMs through Ollama
- Financial data APIs
- Specialized investment analyst agents
- Portfolio management logic
- Risk management agents


Current Host Environment:

OS:
Kubuntu Linux

Hardware:
- AMD Ryzen AI 9 HX 370
- 32GB RAM
- NVIDIA RTX 4050 Laptop GPU
- CUDA enabled
- Ollama local inference


---

# 1. Initial Repository Setup

Repository cloned:

~/ai-hedge-fund


Main components:

src/
├── agents/
├── backtesting/
├── data/
├── graph/
├── llm/
├── tools/
├── utils/
└── main.py


Python environment:

Managed by Poetry


Commands:

Install dependencies:

poetry install


Run application:

poetry run python src/main.py --ticker NVDA



---

# 2. AI Agent Architecture


The system uses multiple specialized AI analysts.


Current analysts:

## Fundamental Analyst

Analyzes:

- Revenue growth
- Earnings growth
- ROE
- Margins
- Debt
- Valuation ratios


## Growth Analyst

Analyzes:

- Future growth potential
- Earnings acceleration


## Technical Analyst

Analyzes:

- Trend
- Momentum
- RSI
- Volatility
- Mean reversion


## Sentiment Analyst

Analyzes:

- News
- Insider activity
- Market sentiment


## Warren Buffett Analyst

Focus:

- Business quality
- Economic moat
- Management
- Long term value


## Portfolio Manager

Combines all signals and creates:

BUY
SELL
SHORT
COVER
HOLD


## Risk Management Agent

Controls:

- Position sizing
- Maximum exposure
- Trade limits



---

# 3. Ollama Local AI Integration


Initially the project only displayed API models:

src/llm/api_models.json


Example:

- GPT
- Claude
- Gemini
- Grok


Problem:

Local Ollama models were not appearing.



---

# 4. Adding Ollama Models


File modified:

src/llm/ollama_models.json


Original provider mapping:

```json
{
"provider":"Alibaba"
}
Problem:

The application expected:

ModelProvider.OLLAMA

Fixed all local models to:

{
"provider":"Ollama"
}

Added models:

qwen3:4b
qwen3:8b
qwen3:30b-a3b
llama3.1
gemma3
mistral
5. Ollama Model Testing

Installed:

langchain-ollama

Verified:

poetry add langchain-ollama

Package already existed.

Ollama models available:

Example:

ollama list

Current working model:

qwen3:8b

6. First Successful AI Hedge Fund Run

Command:

poetry run python src/main.py --ticker NVDA

Selected:

Warren Buffett
Technical Analyst
Fundamentals Analyst
Growth Analyst
Sentiment Analyst

Model:

Qwen 3 (8B)

Result:

Technical Analyst:

Signal:
NEUTRAL

Fundamentals:

Signal:
BULLISH

Reason:

ROE:
114.29%

Net Margin:
62.97%

Operating Margin:
65.60%

Revenue Growth:

85.20%

Earnings Growth:

214.50%

Portfolio Manager:

Decision:

BUY

Quantity:

68 shares

Confidence:

50%

7. Problem Encountered

Attempted:

qwen3:30b-a3b

Error:

model 'qwen3:30b-a3b' not found

Cause:

Model was listed in configuration but not installed locally.

Solution:

Check:

ollama list

Pull missing models:

ollama pull qwen3:30b-a3b
8. Current Database Layer

Already installed:

SQLAlchemy

Alembic

Purpose:

Future database support for:

Historical stock analysis
Portfolio tracking
AI decisions
Backtesting results
Model performance
9. Current Data Models

Located:

src/data/models.py

Contains:

Price

Stores:

Open
Close
High
Low
Volume

FinancialMetrics

Stores:

Market cap
P/E
P/B
Margins
ROE
Growth

InsiderTrade

Stores:

Executive transactions

CompanyNews

Stores:

News
Sentiment

Portfolio

Stores:

Cash
Shares
Positions
10. Current Development Status

Completed:

✅ Project installed

✅ Poetry environment working

✅ Ollama integration working

✅ Qwen3 local model working

✅ Multi-agent analysis working

✅ NVDA analysis completed

✅ Portfolio decision generation working

11. Next Development Phase
Phase 1

Database:

Add PostgreSQL/SQLite storage.

Store:

Every analysis
Every trade decision
Every confidence score
Phase 2

Create Dashboard

Possible stack:

FastAPI
React
Streamlit

Display:

AI recommendations
Portfolio
Historical performance
Phase 3

Backtesting

Test:

"How would the AI have performed over 5 years?"

Metrics:

Sharpe ratio
Maximum drawdown
Win rate
Alpha
Phase 4

Local AI Optimization

Models:

RTX 4050 optimized:

Qwen3 8B
Qwen3 14B
Qwen3 30B MoE

Use larger models through:

Quantization
GPU acceleration
Remote inference
Current Goal

Transform this project from:

"AI stock analyzer"

into:

"Personal autonomous AI hedge fund research platform"


---

Before we write it to disk, I would also add one more section:

**"Project NOMAD + AI Hedge Fund Integration Plan"**

because your setup is actually becoming a serious local AI lab:

- Kubuntu host
- RTX GPU
- Ollama
- Project NOMAD
- Docker
- Local models
- Stock agents


