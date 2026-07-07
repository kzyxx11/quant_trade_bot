import os
import time
import html
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests

# 1. Securely read environment variables (without compromising privacy).
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

# ETF config: ticker -> display name, currency code, currency symbol
ETFS = {
    'CSPX.L': {'name': 'CSPX (iShares Core S&P 500)', 'currency': 'GBP', 'sign': '£'},
    'QQQM':   {'name': 'QQQM (Invesco NASDAQ 100)',   'currency': 'USD', 'sign': '$'},
}

MIN_ROWS_REQUIRED = 200  # need at least 200 trading days for a valid MA200


def get_etf_data():
    print("Fetching the latest historical data from Yahoo Finance...")
    data_dict = {}

    for ticker, meta in ETFS.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="2y")  # 2 years of data for a robust moving average
        except Exception as e:
            print(f"Warning: failed to fetch data for {ticker} ({e}). Skipping this ETF.")
            continue

        if df is None or df.empty:
            print(f"Warning: no data returned for {ticker}. Skipping this ETF.")
            continue

        df = df.dropna(subset=['Close'])

        if len(df) < MIN_ROWS_REQUIRED:
            print(f"Warning: only {len(df)} rows of data for {ticker}, "
                  f"need at least {MIN_ROWS_REQUIRED} for a reliable MA200. Skipping this ETF.")
            continue

        # Calculate MA50 and MA200
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()

        # Use the most recent year of data for charting (fall back to all available rows if fewer)
        df_recent = df.iloc[-252:] if len(df) >= 252 else df

        if pd.isna(df_recent['MA50'].iloc[-1]) or pd.isna(df_recent['MA200'].iloc[-1]):
            print(f"Warning: MA50/MA200 could not be computed for {ticker} (insufficient data). Skipping.")
            continue

        data_dict[ticker] = {"df": df_recent, "name": meta['name'],
                              "currency": meta['currency'], "sign": meta['sign']}

    return data_dict


def generate_chart(data_dict):
    if not data_dict:
        print("No data available, skipping chart generation.")
        return None

    print("Generating dual moving average trend chart...")
    tickers = list(data_dict.keys())
    fig, axes = plt.subplots(len(tickers), 1, figsize=(12, 4 * len(tickers)), sharex=False)

    if len(tickers) == 1:
        axes = [axes]

    colors = ['#1e6091', '#d90429']

    for ax, ticker, color in zip(axes, tickers, colors):
        info = data_dict[ticker]
        df = info['df']
        sign = info['sign']

        ax.plot(df.index, df['Close'], color=color, linewidth=2, label='Price')
        ax.plot(df.index, df['MA50'], color='#52b788', linestyle='--', label='MA50 (Mid-term)')
        ax.plot(df.index, df['MA200'], color='#b7094c', linestyle='-', linewidth=2, label='MA200 (Long-term)')
        ax.fill_between(df.index, df['Close'], color=color, alpha=0.05)
        ax.set_title(info['name'], fontsize=12, loc='left', weight='bold')
        ax.set_ylabel(f"Price ({info['currency']})")
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(loc='upper left')
        ax.text(df.index[-1], df['Close'].iloc[-1], f" {sign}{df['Close'].iloc[-1]:.2f}",
                color=color, weight='bold')

    axes[-1].set_xlabel("Date")
    plt.suptitle("ETF Strategy Monitor: MA50 & MA200 Trend Filter", fontsize=14, weight='bold')
    plt.tight_layout()

    chart_path = "etf_trend.png"
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return chart_path


def build_message(data_dict):
    """
    Builds an HTML-formatted message for Telegram.
    HTML parse_mode is used instead of Markdown/MarkdownV2 because Telegram's
    MarkdownV2 requires escaping a long list of special characters (. ! - ( ) etc.),
    which is error-prone. HTML only requires escaping &, <, and >.
    """
    if not data_dict:
        return "⚠️ <b>ETF Trend Monitor</b>\n\nNo data could be retrieved this run. Please check the data source or try again later."

    msg = "📊 <b>ETF Dual Moving Average Trend Monitor</b>\n\n"

    for ticker, info in data_dict.items():
        df = info['df']
        name = html.escape(info['name'])
        currency = info['currency']
        sign = info['sign']

        close_price = df['Close'].iloc[-1]
        ma50 = df['MA50'].iloc[-1]
        ma200 = df['MA200'].iloc[-1]

        dev50 = ((close_price - ma50) / ma50) * 100
        dev200 = ((close_price - ma200) / ma200) * 100

        # Core three-zone strategy logic
        if close_price < ma50 and close_price > ma200:
            status_text = (
                "🚨 <b>Pullback buy signal</b>\n"
                "Price has dipped below the 50-day moving average (MA50) but is still holding "
                "above the 200-day long-term moving average (MA200) — a favorable entry zone "
                "for dollar-cost averaging."
            )
        elif close_price < ma200:
            status_text = (
                "🔻 <b>High alert: deep pullback</b>\n"
                "Price has broken below the 200-day long-term trend line, signaling a deep "
                "downturn. Consider spacing out purchases into smaller increments and avoid "
                "committing all capital at once."
            )
        else:
            status_text = (
                "✅ <b>Healthy uptrend</b>\n"
                "Price is trading above both moving averages. The trend remains strong — "
                "continue with the regular investment plan."
            )

        msg += f"<b>{name}</b>\n"
        msg += f"{status_text}\n"
        msg += f"  - Latest close: {sign}{close_price:.2f} ({currency})\n"
        msg += f"  - MA50 (mid-term): {sign}{ma50:.2f} (deviation: {dev50:.1f}%)\n"
        msg += f"  - MA200 (long-term): {sign}{ma200:.2f} (deviation: {dev200:.1f}%)\n\n"

    return msg


def send_to_telegram(chart_path, text_msg, retries=3, backoff_seconds=5):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Error: environment variable TG_BOT_TOKEN or TG_CHAT_ID not set. Please configure it first.")
        return

    print("Sending update to Telegram...")
    photo_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    text_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for attempt in range(1, retries + 1):
        try:
            if chart_path and os.path.exists(chart_path):
                with open(chart_path, 'rb') as photo:
                    payload = {'chat_id': CHAT_ID, 'caption': text_msg, 'parse_mode': 'HTML'}
                    files = {'photo': photo}
                    response = requests.post(photo_url, data=payload, files=files, timeout=30)
            else:
                # No chart available (e.g. all ETFs failed to fetch) — send text only
                payload = {'chat_id': CHAT_ID, 'text': text_msg, 'parse_mode': 'HTML'}
                response = requests.post(text_url, data=payload, timeout=30)

            if response.status_code == 200:
                print("Telegram message sent successfully!")
                return
            else:
                print(f"Telegram push failed (attempt {attempt}/{retries}): "
                      f"status={response.status_code}, reason={response.text}")

        except requests.RequestException as e:
            print(f"Network error while sending to Telegram (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            time.sleep(backoff_seconds)

    print("Error: all retry attempts to send the Telegram message have failed.")


if __name__ == "__main__":
    data = get_etf_data()
    path = generate_chart(data)
    message = build_message(data)
    send_to_telegram(path, message)
