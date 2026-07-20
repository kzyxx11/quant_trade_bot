# Quant Trade Bot

**Daily automated analysis for CSPX and QQQM — Trend Score, Momentum Score, and historical win rates based on 15 years of market data.**

---

## Latest Snapshot

![daily update](https://imgur.com/a/EhjyK0D)

Example output:

📜 Historical Match: 138 occurrences
• Next 90d: Win 84.1% | Avg +5.9% | MaxDD -18.4%
• Next 180d: Win 76.1% | Avg +9.1% | MaxDD -18.0%

---

## How It Works (Short Version)

1. **Fetch 15 years** of daily price data for CSPX and QQQM (via `yfinance`).
2. **Calculate** MA50, MA200, and RSI(14) for each day.
3. **Build composite scores:**
   - `Trend Score (0–100)` – measures structural health
   - `Momentum Score (0–100)` – measures short-term strength
4. **Scan history** for days with similar scores (within ±8 points).
5. **Aggregate forward returns** for the matched periods — 90 days and 180 days out.

The result is a probability-based view of current market structure, not a prediction.

---

## Tech Stack

| Component | Tool |
|---|---|
| Data source | Yahoo Finance (`yfinance`) |
| Calculation engine | Python (pandas, matplotlib) |
| Scheduling & execution | GitHub Actions (cron + on-demand) |
| API gateway | Cloudflare Workers |
| Delivery | Telegram Bot API |
| Source code | GitHub (MIT) |

All services are **serverless and free** — total running cost: $0/month.

---

## What's Next

- Add more ETFs (EEM, VTI, etc.)
- Introduce a Volatility Score (ATR)
- Build a simple public dashboard
- Expand to individual stocks (optional)

---

## Links

- **GitHub repo:** [github.com/kzyxx11/quant_trade_bot](https://github.com/kzyxx11/quant_trade_bot)
- **Telegram channel:** [@ETF_Trend_Monitor](https://t.me/ETF_Trend_Monitor) (daily updates)
- **Blog post (Dev.to):** (https://dev.to/kzyxx11/how-i-built-a-serverless-etf-backtest-bot-with-github-actions-and-telegram-3g20)
- **Blog post (Medium):** (https://medium.com/@erickhoo1104/how-i-built-a-serverless-etf-backtest-bot-with-github-actions-and-telegram-2812ab010f98)

---

*Built by Eric Khoo. Not financial advice — just data.*
