Stop guessing. Start knowing.

# Quant Trade Bot – Telegram Bot for ETF Analysis

[![Join Telegram Channel](https://img.shields.io/badge/Join-Telegram%20Channel-0088cc?style=for-the-badge&logo=telegram)](https://t.me/ETF_Trend_Monitor)
[![Try the Bot](https://img.shields.io/badge/Try%20Bot-on%20Telegram-26A5E4?style=for-the-badge&logo=telegram)](https://t.me/MyQuantTrackerBot)

📊 **Live Status:** [![Daily Run](https://github.com/kzyxx11/quant_trade_bot/actions/workflows/run_bot.yml/badge.svg)](https://github.com/kzyxx11/quant_trade_bot/actions)

---

A complete Telegram bot that analyzes ETF trends, momentum, and historical probabilities for long-term investors.

**Built with Python, GitHub Actions, and Cloudflare Workers — all serverless and free.**

👉 **Telegram Bot:** [@MyQuantTrackerBot](https://t.me/MyQuantTrackerBot)  
📢 **Public Channel:** [@ETF_Trend_Monitor](https://t.me/ETF_Trend_Monitor)  
📅 **Daily update:** around 07:30 GMT+8 (after US market close)

📝 Read the full story: [Dev.to](https://dev.to/kzyxx11/how-i-built-a-serverless-etf-backtest-bot-with-github-actions-and-telegram-3g20) | [Medium](https://medium.com/@erickhoo1104/how-i-built-a-serverless-etf-backtest-bot-with-github-actions-and-telegram-2812ab010f98?sharedUserId=erickhoo1104)

---

## Commands

| Command | Description |
|---|---|
| `/check` | Full analysis report (chart + text) |
| `/price` | Latest price, MA50, MA200, and RSI |
| `/stats` | Trend Score and Momentum Score |
| `/chart` | Only the chart (no text) |
| `/subscribe` | Enable daily push notifications |
| `/unsubscribe` | Disable daily push notifications |
| `/about` | Project info |
| `/help` | Show all commands |

---

## How to Use

1. Add the bot on Telegram: [@MyQuantTrackerBot](https://t.me/MyQuantTrackerBot)
2. Send `/start` or `/help` to see available commands
3. Send `/check` to get the full analysis
4. Send `/subscribe` to receive daily updates automatically

**No sign-up. No paywall. No spam.**

---

## What It Does

The bot tracks major global ETFs and provides:

- **Trend Score (0–100)** – Where is the market structure right now?
- **Momentum Score (0–100)** – How strong is the current move?
- **Historical Match** – When this structure appeared before, what happened next?
- **Multi‑scenario alerts** – Normal, Market Update, Market Alert, Special Report
- **Subscription system** – Users can opt in/out of daily updates

---

## Why It's Different

Most investment tools tell you what *they think* will happen.  
This tool tells you what *historically happened* when the market looked like this.

Example output:

📜 Historical Match: 138 similar cases
• Next 90d: Win 84.1% | Avg +5.9% | MaxDD -18.4%
• Next 180d: Win 76.1% | Avg +9.1% | MaxDD -18.0%


That's not a prediction. That's data.

---

## Currently Tracked Assets

| Ticker | Name |
|---|---|
| CSPX.L | iShares Core S&P 500 UCITS ETF |
| QQQM | Invesco NASDAQ 100 ETF |

*More assets may be added over time.*

---

## Methodology

The analysis is built on three layers:

1. **Technical Indicators** – MA50, MA200, RSI (14)
2. **Composite Scoring** – Trend Score and Momentum Score (0–100)
3. **Historical Backtesting** – Scans 15 years of data for structurally similar periods and calculates forward returns

---

## Architecture

Telegram User
│ (sends /check)
▼
Cloudflare Worker (webhook gateway)
│ (triggers GitHub Actions)
▼
GitHub Actions (runs Python script)
│ (fetches 15y data, computes scores, generates chart)
▼
Telegram Bot API
│ (delivers chart + text report)
▼
User's Telegram chat


All components are **serverless and free** — no VPS or always‑on server required.

---

## Tech Stack

- Python 3.10 (pandas, matplotlib, yfinance, requests)
- GitHub Actions (scheduled + on‑demand execution)
- Cloudflare Workers (Telegram webhook bridge)
- Telegram Bot API
- Matplotlib (dark‑theme institutional charts)

---

## Feedback & Contact

Found a bug? Have a suggestion?  
Reach out: [@erickhoo11](https://t.me/erickhoo11)

---

## Disclaimer

This tool provides **data and statistical analysis only**.  
It does not constitute financial advice. Always do your own research before making investment decisions.

---

## License

MIT
