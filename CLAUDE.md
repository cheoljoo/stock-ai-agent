# CLAUDE.md - Stock Analysis AI Agent Project

## Project Overview

This is a Korean stock analysis AI agent service that provides real-time stock quotes, technical analysis, fundamental analysis, and AI-powered predictions using AWS Bedrock (Claude) and the Strands Agent SDK.

## Tech Stack

- **Frontend**: Streamlit (Python web framework)
- **AI/ML**: AWS Bedrock (Claude 3.5 Sonnet), Strands Agent SDK, Prophet (time series forecasting)
- **Data**: yfinance (Yahoo Finance API), feedparser (RSS news)
- **Visualization**: Plotly
- **Infrastructure**: AWS CDK (TypeScript)
- **Language**: Python 3.11+

## Project Structure

```
/
├── app.py                 # Main Streamlit web application
├── stock_agent.py         # AI agent tools (backend)
├── requirements.txt       # Python dependencies
├── cdk/                   # AWS CDK infrastructure (TypeScript)
│   ├── lib/
│   │   └── stock-app-stack.ts
│   └── bin/
├── images/                # App screenshots
└── .claude/               # Claude Code settings
```

## Key Files

### app.py
Main Streamlit application with tabs for:
- Real-time stock quotes (Korea/US markets)
- AI-powered stock prediction using Prophet
- Technical analysis (MA, RSI, MACD, Bollinger Bands)
- Fundamental analysis (P/E, P/B, ROE, etc.)
- Peer comparison
- Macro indicators
- News sentiment analysis

### stock_agent.py
Backend module with AI agent tools decorated with `@tool`:
- `get_stock_price()` - Current stock price
- `analyze_stock_trend()` - Technical analysis
- `analyze_company_news()` - News sentiment analysis
- `get_fundamental_analysis()` - Fundamental metrics
- `get_institutional_holders()` - Institutional ownership
- `get_peer_comparison()` - Industry peer comparison
- `get_macro_indicators()` - Macro economic indicators
- `get_market_movers()` - Market movers
- `get_theme_stocks()` - Theme-based stock screening
- `get_dividend_info()` - Dividend information

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run Streamlit app locally
streamlit run app.py

# Run CLI mode (direct agent interaction)
python stock_agent.py

# Deploy infrastructure
cd cdk && cdk deploy
```

## Korean Stock Ticker Format

Korean stocks use 6-digit codes with `.KS` suffix:
- Samsung Electronics: `005930.KS`
- SK Hynix: `000660.KS`
- Naver: `035420.KS`
- Kakao: `035720.KS`

## Coding Conventions

- **Language**: All comments and docstrings are in Korean
- **Encoding**: UTF-8 with explicit reconfiguration for Windows compatibility
- **Error Handling**: All yfinance API calls wrapped in try-except with user-friendly Korean error messages
- **Division Safety**: Always check for zero division in financial calculations

## AWS Configuration

- **Region**: us-east-1
- **Model**: us.anthropic.claude-3-5-sonnet-20241022-v2:0
- **Infrastructure**: AWS CDK (TypeScript) in `cdk/` directory

## Important Notes

1. **Company Name Handling**: The `TICKER_MAP` dictionary maps Korean company names to ticker symbols. Never translate company names - pass them exactly as user input.

2. **Sentiment Analysis**: Uses keyword-based NLP with weighted positive/negative keywords for news analysis.

3. **Technical Indicators**: RSI, MACD, Bollinger Bands calculations handle edge cases (insufficient data, zero division).

4. **Response Format**: AI responses should be in Korean with specific formats for Korean vs US stocks (won vs dollar).
