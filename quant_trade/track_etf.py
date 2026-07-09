import html
import os
import time
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
            df = yf.Ticker(ticker).history(period="2y", auto_adjust=False)
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

        # Calculate Technical Vectors
        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()
        
        # Native High-Precision RSI (14) Engine
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
            "name": meta["name"],
            "currency": meta["currency"],
            "symbol": meta["symbol"],
        }

    return data


def classify_trend(close_price, ma50, ma200, rsi):
    # Base Trend Structure
    if close_price <= ma200:
        trend_status = {
            "emoji": "🚨",
            "label": "Risk Warning",
            "headline": "Price has broken below the long-term structural trend line.",
        }
    elif close_price < ma50:
        trend_status = {
            "emoji": "🟡",
            "label": "Pullback Buy Zone",
            "headline": "Price is below MA50 but securely holding above MA200.",
        }
    else:
        trend_status = {
            "emoji": "✅",
            "label": "Healthy Uptrend",
            "headline": "Price is trading smoothly above both moving averages.",
        }

    # Contextual Overlay of RSI Overbought/Oversold Signals
    if rsi >= 70:
        trend_status["detail"] = f"⚠️ [OVERBOUGHT ALERT] RSI (14) has scaled to {rsi:.1f}. Momentum is overextended; chasing entries carries elevated short-term risk."
    elif rsi <= 30:
        trend_status["detail"] = f"🔥 [OVERSOLD ALERT] RSI (14) has collapsed to {rsi:.1f}. Extreme fear detected; structurally this represents a high-probability entry zone."
    else:
        trend_status["detail"] = f"RSI (14) is stable at {rsi:.1f}. Market momentum remains balanced within the current trend structure."

    return trend_status


def generate_chart(data):
    if not data:
        print("No valid ETF data available. Skipping chart generation.")
        return None

    print("Generating Multi-Pane Institutional Analytics Canvas...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    plt.style.use('dark_background')
    tickers = list(data.keys())
    
    # Dual-pane architecture per ticker: Price Main Plot (Ratio 3.5) + RSI Oscillator Plot (Ratio 1.0)
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
        # Map specific row locations for Main Plot and RSI Subplot
        main_ax = axes[idx * 2]
        rsi_ax = axes[idx * 2 + 1]
        
        info = data[ticker]
        df = info["df"]

        latest_close = df["Close"].iloc[-1]
        latest_ma50 = df["MA50"].iloc[-1]
        latest_ma200 = df["MA200"].iloc[-1]
        latest_rsi = df["RSI"].iloc[-1]
        dev200 = ((latest_close - latest_ma200) / latest_ma200) * 100
        trend = classify_trend(latest_close, latest_ma50, latest_ma200, latest_rsi)

        # ------------------ Pane 1: Price Structure Canvas ------------------
        main_ax.plot(df.index, df["Close"], color="#ffffff", linewidth=1.5, label="Spot Price", alpha=0.9)
        main_ax.plot(df.index, df["MA50"], color="#ffb703", linestyle="--", linewidth=1.2, label="MA50 (Mid-term)")
        main_ax.plot(df.index, df["MA200"], color="#219ebc", linewidth=1.5, label="MA200 (Structural)")

        # Golden Accumulation Zone Fill
        main_ax.fill_between(
            df.index, df["MA50"], df["MA200"],
            where=(df["Close"] > df["MA200"]) & (df["Close"] < df["MA50"]),
            color="#ffb703", alpha=0.08, label="Golden Accumulation Zone"
        )

        # Main Geometry & Typography Styling
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
        
        # Upper Right Micro Analytics Matrix Box
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

        # ------------------ Pane 2: RSI Relative Strength Subplot ------------------
        rsi_ax.plot(df.index, df["RSI"], color="#8338ec", linewidth=1.2, label="RSI (14)", alpha=0.85)
        
        # Horizontal Threshold Guides
        rsi_ax.axhline(70, color="#d90429", linestyle=":", linewidth=1.0, alpha=0.6)
        rsi_ax.axhline(30, color="#00b4d8", linestyle=":", linewidth=1.0, alpha=0.6)
        
        # Overbought / Oversold Dynamic Background Shading
        rsi_ax.fill_between(df.index, df["RSI"], 70, where=(df["RSI"] >= 70), color="#d90429", alpha=0.15)
        rsi_ax.fill_between(df.index, df["RSI"], 30, where=(df["RSI"] <= 30), color="#00b4d8", alpha=0.15)
        
        # RSI Grid Layout Configuration
        rsi_ax.spines['top'].set_visible(False)
        rsi_ax.spines['right'].set_visible(False)
        rsi_ax.spines['left'].set_color('#444444')
        rsi_ax.spines['bottom'].set_color('#444444')
        rsi_ax.set_ylim(15, 85)
        rsi_ax.set_yticks([30, 50, 70])
        rsi_ax.grid(True, linestyle=":", alpha=0.1, color='#888888')
        rsi_ax.set_ylabel("RSI (14)", color="#888888", fontsize=9)
        rsi_ax.tick_params(axis='both', colors='#888888', labelsize=8)
        
        # Ensure correct date formatting across timelines
        main_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        rsi_ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    fig.suptitle("INSTITUTIONAL QUANTITATIVE ASSET MULTI-PANE MONITOR", fontsize=13, weight="bold", color="#ffffff")
    fig.savefig(CHART_PATH, dpi=300, facecolor='#0d1117', edgecolor='none')
    plt.close(fig)

    print(f"[Success] Expanded asset architecture with RSI subplot exported to {CHART_PATH}")
    return CHART_PATH


def build_message(data):
    if not data:
        return (
            "⚠️ <b>ETF Trend Monitor</b>\n\n"
            "No valid ETF data was retrieved in this run."
        )

    message_parts = ["📊 <b>ETF Dual Moving Average & Momentum Monitor</b>"]

    for ticker, info in data.items():
        df = info["df"]
        close_price = df["Close"].iloc[-1]
        ma50 = df["MA50"].iloc[-1]
        ma200 = df["MA200"].iloc[-1]
        rsi = df["RSI"].iloc[-1]
        
        dev50 = ((close_price - ma50) / ma50) * 100
        dev200 = ((close_price - ma200) / ma200) * 100
        trend = classify_trend(close_price, ma50, ma200, rsi)

        name = html.escape(info["name"])
        symbol = info["symbol"]
        currency = html.escape(info["currency"])

        message_parts.append(
            "\n".join(
                [
                    f"<b>{name}</b>",
                    f"{trend['emoji']} <b>{html.escape(trend['label'])}</b>",
                    html.escape(trend["headline"]),
                    f"<i>{html.escape(trend['detail'])}</i>",
                    f"• Latest close: {symbol}{close_price:.2f} ({currency})",
                    f"• MA50: {symbol}{ma50:.2f} ({dev50:+.1f}%)",
                    f"• MA200: {symbol}{ma200:.2f} ({dev200:+.1f}%)",
                ]
            )
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

    photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    text_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for attempt in range(1, retries + 1):
        try:
            if chart_path and Path(chart_path).exists():
                with Path(chart_path).open("rb") as photo:
                    caption = text_message if len(text_message) <= TELEGRAM_CAPTION_LIMIT else "📊 ETF trend update"
                    post_telegram_request(
                        photo_url,
                        {
                            "chat_id": CHAT_ID,
                            "caption": caption,
                            "parse_mode": "HTML",
                        },
                        files={"photo": photo},
                    )

                if len(text_message) <= TELEGRAM_CAPTION_LIMIT:
                    print("Telegram chart and caption sent successfully.")
                    return True

            for message_part in split_telegram_message(text_message):
                post_telegram_request(
                    text_url,
                    {
                        "chat_id": CHAT_ID,
                        "text": message_part,
                        "parse_mode": "HTML",
                    },
                )

            print("Telegram update sent successfully.")
            return True

        except requests.RequestException as error:
            print(f"Telegram send failed on attempt {attempt}/{retries}: {error}")

        if attempt < retries:
            time.sleep(backoff_seconds)

    print("Error: all Telegram send attempts failed.")
    return False


def main():
    data = fetch_etf_data()
    chart_path = generate_chart(data)
    message = build_message(data)
    send_to_telegram(chart_path, message)


if __name__ == "__main__":
    main()
