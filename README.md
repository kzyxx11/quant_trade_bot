# 🤖 Cloud-Native Dual-MA Trend Filter

[![Live Quant Bot](https://github.com/kzyxx11/quant_trade_bot/actions/workflows/run_bot.yml/badge.svg)](https://github.com/asuki11/quant_trade_bot/actions)
[![Language](https://img.shields.io/badge/language-Python%20%7C%20PineScript%20v5-blue.svg)](https://github.com/asuki11/quant_trade_bot)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A lightweight, serverless ETF trend-monitoring pipeline that tracks medium- and long-term market structure using the 50-day and 200-day moving averages. It fetches market data from Yahoo Finance, generates updated charts, classifies each ETF into a trend zone, and sends the result to Telegram automatically.

What It Does
· Tracks global ETFs such as QQQM and CSPX.L
· Calculates MA50 and MA200 from the latest historical prices
· Classifies each ETF into a simple three-zone trend model
· Generates a clean Matplotlib trend chart
· Sends the chart and strategy summary to Telegram
· Runs automatically on GitHub Actions with no server to manage

---

## 🏗️ System Architecture

```text
Yahoo Finance
    |
    | Fetch 2 years of historical ETF prices
    v
GitHub Actions
    |
    +--> Data cleaning and moving-average calculation
    |
    +--> Matplotlib chart generation
    |
    +--> Strategy classification and deviation summary
    v
Telegram Bot API
    |
    v
Mobile push notification

📈 Strategy Logic
The model filters short-term noise by comparing the latest closing price with two trend references:

✅ Bullish Trend: Price >= MA50
Price is above the medium-term trend line, suggesting strong upward momentum.

🚨 Pullback Buy Zone: MA200 < Price < MA50
Price has pulled back below MA50 while still holding above MA200. This is treated as a potential accumulation zone.

💥 Bearish / Risk Zone: Price <= MA200
Price has broken below the long-term trend line, suggesting weaker market structure and higher downside risk.

This project is intended for monitoring and research only. It is not financial advice.

📁 Repository Structure
.github/workflows/run_bot.yml — GitHub Actions workflow (Runs daily at 22:30 UTC).
track_etf.py — Core data, charting, and Telegram alert script.
tradingview/etf_trend_filter.ps - TradingView Pine Script dashboard

🛠️ Technical Notes
· Serverless automation: Runs on GitHub Actions, so no VPS or always-on machine is required.
· Secure credentials: Telegram credentials are loaded from GitHub repository secrets.
· Data cleaning: Missing closing prices are removed before moving averages are calculated.
· ETF-aware display: Each ETF can define its own display name, quote currency, and currency symbol.
· Chart-first alerts: Telegram receives both a visual trend chart and a structured strategy summary.

GitHub Secrets
Create the following repository secrets before running the workflow:

TG_BOT_TOKEN
TG_CHAT_ID

Schedule
The workflow runs daily at 22:30 UTC, which is 06:30 in Kuala Lumpur. This is designed to run after the US market close.

📬 Author
Developed by Eric Khoo.
Open to quantitative development, custom Pine Script indicators, and automated data-pipeline projects.
