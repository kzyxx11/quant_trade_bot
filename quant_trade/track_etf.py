import html
import os
import time
from datetime import datetime
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests
import yfinance as yf

TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

MIN_ROWS_REQUIRED = 200
CHART_LOOKBACK_ROWS = 252
OUTPUT_DIR = Path("outputs")
CHART_PATH = OUTPUT_DIR / "etf_trend.png"
TELEGRAM_CAPTION_LIMIT = 1024

ETFS = {
    "CSPX.L": {
        "name": "CSPX (iShares Core S&P 500 UCITS ETF)",
        "currency": "USD",
        "symbol": "$",
    },
    "QQQM": {
        "name": "QQQM (Invesco NASDAQ 100 ETF)",
        "currency": "USD",
        "symbol": "$",
    },
}


def fetch_etf_data():
    print("Fetching latest ETF price data from Yahoo Finance...")
    data = {}

    for ticker, meta in ETFS.items():
        try:
            df = yf.Ticker(ticker).history(period="15y", auto_adjust=False)
        except Exception as error:
            print(f"Warning: failed to fetch {ticker}: {error}")
            continue

        if df is None or df.empty:
            print(f"Warning: no data returned for {ticker}.")
            continue

        df = df.dropna(subset=["Close"]).copy()

        if len(df) < MIN_ROWS_REQUIRED:
            print(
                f"Warning: {ticker} has only {len(df)} valid rows; "
                f"{MIN_ROWS_REQUIRED} rows are required for calculations."
            )
            continue

        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()

        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df["RSI"] = 100 - (100 / (1 + rs))

        df = df.dropna(subset=["MA50", "MA200", "RSI"])

        if df.empty:
            print(f"Warning: technical attributes could not be computed for {ticker}.")
            continue

        data[ticker] = {
            "df": df.tail(CHART_LOOKBACK_ROWS),
            "df_full": df,
            "name": meta["name"],
            "currency": meta["currency"],
            "symbol": meta["symbol"],
        }

    return data


def calculate_trend_score(close_price, ma50, ma200):
    score = 50
    if close_price > ma200:
        score += 20
        dist200 = ((close_price - ma200) / ma200) * 100
        score += min(dist200 * 1.5, 15)
    else:
        score -= 20
        dist200 = ((ma200 - close_price) / ma200) * 100
        score -= min(dist200 * 1.5, 15)

    if close_price > ma50:
        score += 10
    else:
        score -= 10

    if ma50 > ma200:
        score += 5
    else:
        score -= 5

    return max(0, min(100, round(score)))


def calculate_momentum_score(rsi_series):
    latest_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-6] if len(rsi_series) >= 6 else rsi_series.iloc[0]
    rsi_change = latest_rsi - prev_rsi

    score = latest_rsi
    score += max(min(rsi_change * 0.8, 10), -10)

    return max(0, min(100, round(score)))


def run_historical_analysis(df, current_trend_score, current_momentum_score,
                             lookforward_days=[90, 180], tolerance=8):
    df_copy = df.copy()
    df_copy['MA50'] = df_copy['Close'].rolling(window=50).mean()
    df_copy['MA200'] = df_copy['Close'].rolling(window=200).mean()

    delta = df_copy['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df_copy['RSI'] = 100 - (100 / (1 + rs))

    df_clean = df_copy.dropna(subset=['Close', 'MA50', 'MA200', 'RSI']).copy()
    if len(df_clean) < 500:
        return {"error": "Insufficient historical data (need at least 500 trading days)."}

    match_dates = []

    for i in range(250, len(df_clean) - max(lookforward_days)):
        row = df_clean.iloc[i]
        close = row['Close']
        ma50 = row['MA50']
        ma200 = row['MA200']
        rsi = row['RSI']

        trend_score = calculate_trend_score(close, ma50, ma200)

        if i >= 6:
            prev_rsi = df_clean.iloc[i-6]['RSI'] if i-6 >=0 else rsi
        else:
            prev_rsi = rsi
        rsi_change = rsi - prev_rsi
        momentum_score = min(100, max(0, round(rsi + rsi_change * 0.8)))

        if (abs(trend_score - current_trend_score) <= tolerance and
            abs(momentum_score - current_momentum_score) <= tolerance):
            match_dates.append(i)

    if not match_dates:
        return {"error": "No matching historical structure found."}

    results = {}
    for days in lookforward_days:
        returns = []
        for idx in match_dates:
            start_price = df_clean.iloc[idx]['Close']
            end_idx = min(idx + days, len(df_clean) - 1)
            end_price = df_clean.iloc[end_idx]['Close']
            ret = (end_price / start_price) - 1
            returns.append(ret)

        if returns:
            avg_ret = sum(returns) / len(returns) * 100
            positive_count = sum(1 for r in returns if r > 0)
            win_rate = positive_count / len(returns) * 100
            max_drawdown = min(returns) * 100 if returns else 0
            results[days] = {
                "count": len(returns),
                "avg_return": round(avg_ret, 1),
                "win_rate": round(win_rate, 1),
                "max_dd": round(max_drawdown, 1)
            }
        else:
            results[days] = {"error": "No valid data"}

    return {
        "match_count": len(match_dates),
        "periods": results
    }


def get_market_state(close_price, ma50, ma200):
    above_ma50 = close_price > ma50
    above_ma200 = close_price > ma200

    if above_ma50 and above_ma200:
        return {
            "emoji": "✅",
            "label": "Healthy Uptrend",
            "trend_text": "Price is trading above both MA50 and MA200 — structurally bullish and confirmed.",
        }
    if above_ma200 and not above_ma50:
        return {
            "emoji": "🟡",
            "label": "Pullback Buy Zone",
            "trend_text": "Price has pulled back below MA50 but remains above MA200 — long-term trend intact, short-term cooling off.",
        }
    if not above_ma200 and above_ma50:
        return {
            "emoji": "🟠",
            "label": "Unstable Structure",
            "trend_text": "Price is above MA50 but still below MA200 — a fragile, unconfirmed recovery attempt.",
        }
    return {
        "emoji": "🚨",
        "label": "Risk Warning",
        "trend_text": "Price is trading below both MA50 and MA200 — structurally bearish.",
    }


def explain_scores(momentum_score):
    if momentum_score >= 70:
        momentum_text = "Momentum is strong and accelerating — approaching overbought territory."
    elif momentum_score >= 50:
        momentum_text = "Momentum is balanced, neither overextended nor weak."
    elif momentum_score >= 30:
        momentum_text = "Momentum is soft; buyers are losing short-term control."
    else:
        momentum_text = "Momentum is deeply negative — approaching oversold territory."
    return momentum_text


def classify_trend(close_price, ma50, ma200):
    if close_price <= ma200:
        return {"emoji": "🚨", "label": "Risk Warning"}
    if close_price < ma50:
        return {"emoji": "🟡", "label": "Pullback Buy Zone"}
    return {"emoji": "✅", "label": "Healthy Uptrend"}


def generate_chart(data):
    if not data:
        print("No valid ETF data available. Skipping chart generation.")
        return None

    print("Generating Multi-Pane Institutional Analytics Canvas...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    plt.style.use('dark_background')
    tickers = list(data.keys())

    fig, axes = plt.subplots(
        len(tickers) * 2,
        1,
        figsize=(12, 5.0 * len(tickers) * 2),
        gridspec_kw={'height_ratios': [3.5, 1.0] * len(tickers)},
        constrained_layout=True,
    )

    if len(tickers) * 2 == 2:
        axes = [axes[0], axes[1]]

    for idx, ticker in enumerate(tickers):
        main_ax = axes[idx * 2]
        rsi_ax = axes[idx * 2 + 1]

        info = data[ticker]
        df = info["df"]

        latest_close = df["Close"].iloc[-1]
        latest_ma50 = df["MA50"].iloc[-1]
        latest_ma200 = df["MA200"].iloc[-1]
        latest_rsi = df["RSI"].iloc[-1]
        dev200 = ((latest_close - latest_ma200) / latest_ma200) * 100
        trend = classify_trend(latest_close, latest_ma50, latest_ma200)

        main_ax.plot(df.index, df["Close"], color="#ffffff", linewidth=1.5, label="Spot Price", alpha=0.9)
        main_ax.plot(df.index, df["MA50"], color="#ffb703", linestyle="--", linewidth=1.2, label="MA50 (Mid-term)")
        main_ax.plot(df.index, df["MA200"], color="#219ebc", linewidth=1.5, label="MA200 (Structural)")

        main_ax.fill_between(
            df.index, df["MA50"], df["MA200"],
            where=(df["Close"] > df["MA200"]) & (df["Close"] < df["MA50"]),
            color="#ffb703", alpha=0.08, label="Golden Accumulation Zone"
        )

        main_ax.spines['top'].set_visible(False)
        main_ax.spines['right'].set_visible(False)
        main_ax.spines['left'].set_color('#444444')
        main_ax.spines['bottom'].set_color('#444444')
        main_ax.grid(True, linestyle=":", alpha=0.15, color='#888888')
        main_ax.set_title(
            f"FINANCIAL TREND VECTOR: {ticker.upper()} ({trend['label'].upper()})",
            fontsize=12, fontweight="bold", pad=12, loc="left", color="#ffffff"
        )
        main_ax.set_ylabel(f"Price ({info['currency']})", color="#888888", fontsize=9)

        status_text = (
            f"Live Spot  : {info['symbol']}{latest_close:.2f}\n"
            f"MA50 Nodes : {info['symbol']}{latest_ma50:.2f}\n"
            f"MA200 Nodes: {info['symbol']}{latest_ma200:.2f}\n"
            f"Deviation  : {dev200:+.1f}%"
        )
        main_ax.text(
            0.98, 0.93, status_text,
            transform=main_ax.transAxes, fontsize=8.5, fontfamily='monospace',
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#1e1e1e', edgecolor='#333333', alpha=0.8)
        )
        main_ax.tick_params(axis='both', colors='#888888', labelsize=8.5)
        main_ax.legend(loc="lower left", frameon=True, facecolor='#121212', edgecolor='#222222', fontsize=8.5)

        rsi_ax.plot(df.index, df["RSI"], color="#8338ec", linewidth=1.2, label="RSI (14)", alpha=0.85)
        rsi_ax.axhline(70, color="#d90429", linestyle=":", linewidth=1.0, alpha=0.6)
        rsi_ax.axhline(30, color="#00b4d8", linestyle=":", linewidth=1.0, alpha=0.6)
        rsi_ax.fill_between(df.index, df["RSI"], 70, where=(df["RSI"] >= 70), color="#d90429", alpha=0.15)
        rsi_ax.fill_between(df.index, df["RSI"], 30, where=(df["RSI"] <= 30), color="#00b4d8", alpha=0.15)

        rsi_ax.spines['top'].set_visible(False)
        rsi_ax.spines['right'].set_visible(False)
        rsi_ax.spines['left'].set_color('#444444')
        rsi_ax.spines['bottom'].set_color('#444444')
        rsi_ax.set_ylim(15, 85)
        rsi_ax.set_yticks([30, 50, 70])
        rsi_ax.grid(True, linestyle=":", alpha=0.1, color='#888888')
        rsi_ax.set_ylabel("RSI (14)", color="#888888", fontsize=9)
        rsi_ax.tick_params(axis='both', colors='#888888', labelsize=8)

        main_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        rsi_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    fig.suptitle("INSTITUTIONAL QUANTITATIVE ASSET MULTI-PANE MONITOR", fontsize=13, weight="bold", color="#ffffff")
    fig.savefig(CHART_PATH, dpi=300, facecolor='#0d1117', edgecolor='none')
    plt.close(fig)

    print(f"[Success] Expanded asset architecture with RSI subplot exported to {CHART_PATH}")
    return CHART_PATH


def build_message(data):
    if not data:
        return "⚠️ <b>ETF Trend Monitor</b>\n\nNo valid ETF data was retrieved in this run."

    message_parts = ["📊 <b>ETF Trend &amp; Momentum Monitor</b>"]

    for ticker, info in data.items():
        df = info["df"]
        close_price = df["Close"].iloc[-1]
        ma50 = df["MA50"].iloc[-1]
        ma200 = df["MA200"].iloc[-1]
        rsi = df["RSI"].iloc[-1]

        dev50 = ((close_price - ma50) / ma50) * 100
        dev200 = ((close_price - ma200) / ma200) * 100

        trend_score = calculate_trend_score(close_price, ma50, ma200)
        momentum_score = calculate_momentum_score(df["RSI"])

        historical = run_historical_analysis(
            df=info["df_full"],
            current_trend_score=trend_score,
            current_momentum_score=momentum_score
        )

        hist_text = ""
        if "error" not in historical:
            hist_text += f"\n📜 **Historical Match**: {historical['match_count']} occurrences\n"
            for days, stats in historical['periods'].items():
                if "error" not in stats:
                    hist_text += (
                        f"  • Next {days}d: Win {stats['win_rate']}% | "
                        f"Avg {stats['avg_return']:+.1f}% | "
                        f"MaxDD {stats['max_dd']:.1f}%\n"
                    )
                else:
                    hist_text += f"  • Next {days}d: {stats['error']}\n"
        else:
            hist_text = f"\n📜 **Historical Match**: {historical['error']}"

        market_state = get_market_state(close_price, ma50, ma200)
        trend_text = market_state["trend_text"]
        momentum_text = explain_scores(momentum_score)

        name = html.escape(info["name"])
        symbol = info["symbol"]
        currency = html.escape(info["currency"])

        message_parts.append(
            "\n".join([
                f"<b>{name}</b>",
                "",
                f"📈 <b>Trend Score: {trend_score}/100</b>",
                html.escape(trend_text),
                "",
                f"⚡ <b>Momentum Score: {momentum_score}/100</b>",
                html.escape(momentum_text),
                hist_text,
                "",
                f"• Latest close: {symbol}{close_price:.2f} ({currency})",
                f"• MA50: {symbol}{ma50:.2f} ({dev50:+.1f}%)",
                f"• MA200: {symbol}{ma200:.2f} ({dev200:+.1f}%)",
                f"• RSI (14): {rsi:.1f}",
            ])
        )

    return "\n\n".join(message_parts)


def post_telegram_request(url, payload, files=None):
    response = requests.post(url, data=payload, files=files, timeout=30)
    response.raise_for_status()
    return response


def split_telegram_message(text, limit=3900):
    if len(text) <= limit:
        return [text]

    chunks = []
    current = []
    current_length = 0

    for block in text.split("\n\n"):
        block_length = len(block) + 2
        if current and current_length + block_length > limit:
            chunks.append("\n\n".join(current))
            current = [block]
            current_length = block_length
        else:
            current.append(block)
            current_length += block_length

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def send_to_telegram(chart_path, text_message, retries=3, backoff_seconds=5):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Error: TG_BOT_TOKEN and TG_CHAT_ID must be configured as repository secrets.")
        return False

    public_channel_id = os.getenv("PUBLIC_CHANNEL_ID")
    print(f"[DEBUG] PUBLIC_CHANNEL_ID = '{public_channel_id}'")
    targets = [CHAT_ID]
    if public_channel_id:
        targets.append(public_channel_id)
    print(f"[DEBUG] targets = {targets}")

    photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    text_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    all_success = True

    for target_chat_id in targets:
        success = False
        for attempt in range(1, retries + 1):
            try:
                if chart_path and Path(chart_path).exists():
                    with Path(chart_path).open("rb") as photo:
                        caption = text_message if len(text_message) <= TELEGRAM_CAPTION_LIMIT else "📊 ETF trend update"
                        post_telegram_request(
                            photo_url,
                            {
                                "chat_id": target_chat_id,
                                "caption": caption,
                                "parse_mode": "HTML",
                            },
                            files={"photo": photo},
                        )

                    if len(text_message) <= TELEGRAM_CAPTION_LIMIT:
                        print(f"Telegram chart sent to {target_chat_id} successfully.")
                        success = True
                        break

                for message_part in split_telegram_message(text_message):
                    post_telegram_request(
                        text_url,
                        {
                            "chat_id": target_chat_id,
                            "text": message_part,
                            "parse_mode": "HTML",
                        },
                    )

                print(f"Telegram text sent to {target_chat_id} successfully.")
                success = True
                break

            except requests.RequestException as error:
                print(f"Telegram send failed to {target_chat_id} on attempt {attempt}/{retries}: {error}")
                if attempt < retries:
                    time.sleep(backoff_seconds)

        if not success:
            all_success = False
            print(f"Error: all attempts failed for target {target_chat_id}.")

    return all_success


def generate_html(data, date_str):
    """
    Generate a pure HTML dashboard page with all assets' latest analysis data.
    Output path: docs/index.html, hosted by GitHub Pages.
    """
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quant Trade Bot - Daily Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0d1117;
            color: #e6edf3;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            padding: 20px;
            max-width: 900px;
            margin: 0 auto;
        }
        h1 { font-size: 24px; font-weight: 600; margin-bottom: 6px; }
        .subtitle { color: #8b949e; font-size: 14px; margin-bottom: 24px; }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 18px 20px;
            margin-bottom: 20px;
        }
        .card h2 {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 12px;
            color: #f0f6fc;
        }
        .row {
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            font-size: 14px;
            border-bottom: 1px solid #21262d;
        }
        .row:last-child { border-bottom: none; }
        .label { color: #8b949e; }
        .value { font-weight: 500; }
        .badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 13px;
            font-weight: 500;
        }
        .badge-buy { background: #1a7f37; color: #fff; }
        .badge-hold { background: #9e6a03; color: #fff; }
        .badge-wait { background: #7a2e2e; color: #fff; }
        .footer {
            margin-top: 30px;
            font-size: 13px;
            color: #8b949e;
            text-align: center;
            border-top: 1px solid #21262d;
            padding-top: 20px;
        }
        .footer a { color: #58a6ff; text-decoration: none; }
    </style>
</head>
<body>
    <h1>📊 Quant Trade Bot</h1>
    <div class="subtitle">Daily snapshot · {date}</div>
"""

    for ticker, info in data.items():
        df = info["df"]
        close_price = df["Close"].iloc[-1]
        ma50 = df["MA50"].iloc[-1]
        ma200 = df["MA200"].iloc[-1]

        trend_score = calculate_trend_score(close_price, ma50, ma200)
        momentum_score = calculate_momentum_score(df["RSI"])
        historical = run_historical_analysis(
            df=info["df_full"],
            current_trend_score=trend_score,
            current_momentum_score=momentum_score
        )

        action_text = "⚠️ Insufficient data. Please refer to Trend and Momentum scores."
        badge_class = "badge-hold"

        if "error" not in historical:
            win_rate = historical["periods"].get(90, {}).get("win_rate", 0)
            if trend_score >= 60 and win_rate >= 75:
                action_text = "✅ Historically high win rate for this structure. Consider maintaining or slightly increasing your DCA."
                badge_class = "badge-buy"
            elif trend_score >= 40 and win_rate >= 55:
                action_text = "⏸️ Historically neutral win rate. Maintain your regular DCA pace."
                badge_class = "badge-hold"
            else:
                action_text = "⏳ Historically low win rate. Consider waiting for a clearer signal."
                badge_class = "badge-wait"

        html_template += f"""
    <div class="card">
        <h2>{info['name']}</h2>
        <div class="row"><span class="label">Latest Close</span><span class="value">{info['symbol']}{close_price:.2f}</span></div>
        <div class="row"><span class="label">Trend Score</span><span class="value">{trend_score}/100</span></div>
        <div class="row"><span class="label">Momentum Score</span><span class="value">{momentum_score}/100</span></div>
        <div class="row"><span class="label">Historical Match</span><span class="value">{historical.get('match_count', 'N/A')} occurrences</span></div>
        <div class="row"><span class="label">90-day Win Rate</span><span class="value">{historical.get('periods', {}).get(90, {}).get('win_rate', 'N/A')}%</span></div>
        <div class="row"><span class="label">Suggested Action</span><span class="value"><span class="badge {badge_class}">{action_text}</span></span></div>
    </div>
"""

    html_template += f"""
    <div class="footer">
        Updated daily via GitHub Actions · <a href="https://t.me/ETF_Trend_Monitor" target="_blank">Telegram Channel</a> · <a href="https://github.com/kzyxx11/quant_trade_bot" target="_blank">GitHub</a>
    </div>
</body>
</html>
"""
    return html_template


def main():
    data = fetch_etf_data()
    if not data:
        print("No data fetched. Exiting.")
        return

    chart_path = generate_chart(data)
    message = build_message(data)
    send_to_telegram(chart_path, message)

    # Generate web dashboard
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M (GMT+8)")
    html_content = generate_html(data, today_str)

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    index_path = docs_dir / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[Success] Dashboard updated at {index_path}")


if __name__ == "__main__":
    main()
