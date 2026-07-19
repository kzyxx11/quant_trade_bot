# ETF Trend Monitor – Daily Probability-Based Investment Intelligence

A lightweight, serverless quantitative analysis tool for long-term ETF investors.  
Every trading day, it analyzes market structure, calculates trend and momentum scores, and shows you **historical probabilities** — not opinions.

👉 **Public Channel:** [@ETF_Trend_Monitor](https://t.me/ETF_Trend_Monitor)  
📅 **Daily update:** 06:30 GMT+8 (after US market close)

---

## What It Does

This bot tracks major global ETFs (currently CSPX and QQQM) and provides:

- **Trend Score (0–100)** – Where is the market structure right now?
- **Momentum Score (0–100)** – How strong is the current move?
- **Historical Match** – When this structure appeared before, what happened next?

---

## Why It's Different

Most investment tools tell you what *they think* will happen.  
This tool tells you what *historically happened* when the market looked like this.

Example output:

📜 Historical Match: 138 occurrences
• Next 90d: Win 84.1% | Avg +5.9% | MaxDD -18.4%
• Next 180d: Win 76.1% | Avg +9.1% | MaxDD -18.0%


That's not a prediction. That's data.

---

## How to Use

1. Join the public channel: [@ETF_Trend_Monitor](https://t.me/ETF_Trend_Monitor)
2. Receive daily updates automatically
3. Use the data to inform your own decisions

**No sign-up. No paywall. No spam.**

---

## Supported Assets

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

All calculations are performed serverlessly via GitHub Actions and delivered to Telegram.

---

## Tech Stack

- Python (pandas, matplotlib, yfinance)
- GitHub Actions (scheduled + on-demand execution)
- Cloudflare Workers (Telegram webhook bridge)
- Telegram Bot API

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
