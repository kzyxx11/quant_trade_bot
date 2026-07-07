import html
import os
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import requests
import yfinance as yf


TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

MIN_ROWS_REQUIRED = 200
CHART_LOOKBACK_ROWS = 252
OUTPUT_DIR = Path("outputs")
CHART_PATH = OUTPUT_DIR / "etf_trend.png"


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
                f"{MIN_ROWS_REQUIRED} rows are required for MA200."
            )
            continue

        df["MA50"] = df["Close"].rolling(window=50).mean()
        df["MA200"] = df["Close"].rolling(window=200).mean()
        df = df.dropna(subset=["MA50", "MA200"])

        if df.empty:
            print(f"Warning: moving averages could not be calculated for {ticker}.")
            continue

        data[ticker] = {
            "df": df.tail(CHART_LOOKBACK_ROWS),
            "name": meta["name"],
            "currency": meta["currency"],
            "symbol": meta["symbol"],
        }

    return data


def classify_trend(close_price, ma50, ma200):
    if close_price <= ma200:
        return {
            "label": "Risk Zone",
            "headline": "Price is below the long-term trend line.",
            "detail": (
                "The ETF is trading below MA200, which suggests weaker market "
                "structure. Consider a more defensive allocation or smaller staged entries."
            ),
        }

    if close_price < ma50:
        return {
            "label": "Pullback Buy Zone",
            "headline": "Price is below MA50 but still above MA200.",
            "detail": (
                "The ETF is in a medium-term pullback while the long-term trend "
                "remains intact. This can be monitored as a potential accumulation zone."
            ),
        }

    return {
        "label": "Bullish Trend",
        "headline": "Price is above the medium-term trend line.",
        "detail": (
            "The ETF is trading above MA50 and MA200, which indicates healthy "
            "upward momentum."
        ),
    }


def generate_chart(data):
    if not data:
        print("No valid ETF data available. Skipping chart generation.")
        return None

    print("Generating MA50/MA200 trend chart...")
    OUTPUT_DIR.mkdir(exist_ok=True)

    tickers = list(data.keys())
    fig, axes = plt.subplots(
        len(tickers),
        1,
        figsize=(12, 4.5 * len(tickers)),
        sharex=False,
        constrained_layout=True,
    )

    if len(tickers) == 1:
        axes = [axes]

    price_colors = ["#1E6091", "#D90429", "#6A4C93", "#2A9D8F"]

    for index, ticker in enumerate(tickers):
        ax = axes[index]
        info = data[ticker]
        df = info["df"]
        price_color = price_colors[index % len(price_colors)]

        ax.plot(df.index, df["Close"], color=price_color, linewidth=2, label="Close")
        ax.plot(df.index, df["MA50"], color="#2A9D8F", linestyle="--", linewidth=1.7, label="MA50")
        ax.plot(df.index, df["MA200"], color="#C1121F", linewidth=1.9, label="MA200")
        ax.fill_between(df.index, df["Close"], color=price_color, alpha=0.06)

        latest_close = df["Close"].iloc[-1]
        latest_ma50 = df["MA50"].iloc[-1]
        latest_ma200 = df["MA200"].iloc[-1]
        trend = classify_trend(latest_close, latest_ma50, latest_ma200)

        ax.set_title(f"{info['name']} - {trend['label']}", fontsize=12, loc="left", weight="bold")
        ax.set_ylabel(f"Price ({info['currency']})")
        ax.grid(True, linestyle=":", alpha=0.55)
        ax.legend(loc="upper left")
        ax.annotate(
            f"{info['symbol']}{latest_close:.2f}",
            xy=(df.index[-1], latest_close),
            xytext=(8, 0),
            textcoords="offset points",
            color=price_color,
            weight="bold",
            va="center",
        )

    axes[-1].set_xlabel("Date")
    fig.suptitle("ETF Dual Moving Average Trend Monitor", fontsize=15, weight="bold")
    fig.savefig(CHART_PATH, dpi=160, bbox_inches="tight")
    plt.close(fig)

    return CHART_PATH


def build_message(data):
    if not data:
        return (
            "<b>ETF Trend Monitor</b>\n\n"
            "No valid ETF data was retrieved in this run. Please check Yahoo Finance "
            "availability or try again later."
        )

    message_parts = ["<b>ETF Dual Moving Average Trend Monitor</b>\n"]

    for ticker, info in data.items():
        df = info["df"]
        close_price = df["Close"].iloc[-1]
        ma50 = df["MA50"].iloc[-1]
        ma200 = df["MA200"].iloc[-1]
        dev50 = ((close_price - ma50) / ma50) * 100
        dev200 = ((close_price - ma200) / ma200) * 100
        trend = classify_trend(close_price, ma50, ma200)

        name = html.escape(info["name"])
        symbol = info["symbol"]
        currency = html.escape(info["currency"])

        message_parts.append(
            "\n".join(
                [
                    f"<b>{name}</b>",
                    f"<b>{html.escape(trend['label'])}</b>: {html.escape(trend['headline'])}",
                    html.escape(trend["detail"]),
                    f"Latest close: {symbol}{close_price:.2f} ({currency})",
                    f"MA50: {symbol}{ma50:.2f} | Deviation: {dev50:+.1f}%",
                    f"MA200: {symbol}{ma200:.2f} | Deviation: {dev200:+.1f}%",
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
                    post_telegram_request(
                        photo_url,
                        {
                            "chat_id": CHAT_ID,
                            "caption": "ETF trend chart",
                        },
                        files={"photo": photo},
                    )

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
