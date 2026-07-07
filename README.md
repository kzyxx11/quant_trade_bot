# 🤖 Cloud-Native Dual-MA Trend Filter & Automated Quant Pipeline

[![Live Quant Bot](https://github.com/asuki11/quant_trade_bot/actions/workflows/run_bot.yml/badge.svg)](https://github.com/asuki11/quant_trade_bot/actions)
[![Language](https://img.shields.io/badge/language-Python%20%7C%20PineScript%20v5-blue.svg)](https://github.com/asuki11/quant_trade_bot)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A lightweight, zero-cost quantitative asset monitoring pipeline that automatically tracks mid-to-long-term trends (MA50/MA200) for global ETFs (e.g., QQQM, CSPX) and delivers real-time charts and strategy alerts directly to Telegram.

---

## 🏗️ System Architecture

```text
[Yahoo Finance API]
       │ (Fetch 2-Year historical data)
       ▼
[GitHub Actions (Ubuntu)] ───► [Data Cleaning] ───► [Matplotlib Engine]
       │                                                   │
       ▼ (Parse 3-Quadrant Matrix)                         ▼ (Generate chart)
[Strategy Status & Deviation] ─────────────────────────────┘
       │
       ▼ (TLS Request via Repository Secrets)
[Telegram Bot API] ───► [Mobile Push Notification]

📈 Strategy Logic
The system filters market noise by evaluating the price position relative to MA50 (mid-term momentum) and MA200 (long-term trend):

✅ Bull Market (Strong Trend): Price >= MA50. Strong upward momentum.
🚨 Golden Hitting Zone (Buy Setup): MA200 < Price < MA50. Price retraces below MA50 but holds above the long-term MA200 support. Optimal for spot accumulation.
💥 Bear Market (Risk Warning): Price < MA200. Structural downtrend. Shift to defensive allocation.

📁 Repository Structure
.github/workflows/run_bot.yml — GitHub Actions cron engine (Runs daily at 22:30 UTC).
tradingview/etf_trend_filter.ps — Frontend TradingView dashboard UI (Pine Script v5).
track_etf.py — Core Python processing script (Data fetching, cleaning, and alerting).

🛠️ Key Technical Features
Automated Data Cleaning: Uses pandas.dropna() to automatically fix timezone gaps and settlement anomalies across US and London Stock Exchange (LSE) assets.
Serverless Automation: Fully hosted on GitHub Actions infrastructure; zero hosting costs, secure credential management via GitHub Secrets.
Optimized UI (Pine Script): Frontend dashboard binds exclusively to barstate.islast to prevent historical rendering lag on TradingView charts.

📬 Contact
Developed by asuki11. Open for quantitative development, customized Pine Script indicators, and automated data pipelines.
