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


def calculate_trend_score(close_price, ma50, ma200):
    """
    Trend Score (0-100): Measures structural trend health.
    0-30: Bearish structure | 30-50: Weak/Transitional | 50-70: Constructive | 70-100: Strong uptrend
    """
    score = 50  # neutral baseline

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
    """
    Momentum Score (0-100): Measures short-term momentum strength and direction.
    """
    latest_rsi = rsi_series.iloc[-1]
    prev_rsi = rsi_series.iloc[-6] if len(rsi_series) >= 6 else rsi_series.iloc[0]
    rsi_change = latest_rsi - prev_rsi

    score = latest_rsi
    score += max(min(rsi_change * 0.8, 10), -10)

    return max(0, min(100, round(score)))

def run_historical_analysis(df, current_trend_score, current_momentum_score, 
                             lookforward_days=[90, 180], tolerance=8):
    """
    扫描历史数据，找出所有与"当前趋势/动量结构相似"的日期，
    统计这些日期之后 3 个月和 6 个月的涨跌表现。
    
    Parameters:
        df: 包含 'Close', 'MA50', 'MA200', 'RSI' 列的完整历史 DataFrame
        current_trend_score: 当前计算出的 Trend Score (0-100)
        current_momentum_score: 当前计算出的 Momentum Score (0-100)
        lookforward_days: 列表，例如 [90, 180]，表示统计未来 90 天和 180 天
        tolerance: 分数容忍度，±8 分内都算"相似结构"
    
    Returns:
        dict: 包含匹配次数、各周期的平均收益、上涨概率、最大回撤
    """
    # 确保数据有完整的列
    df_copy = df.copy()
    df_copy['MA50'] = df_copy['Close'].rolling(window=50).mean()
    df_copy['MA200'] = df_copy['Close'].rolling(window=200).mean()
    
    # 计算历史 RSI（14天）
    delta = df_copy['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df_copy['RSI'] = 100 - (100 / (1 + rs))
    
    # 去掉缺失值，防止干扰
    df_clean = df_copy.dropna(subset=['Close', 'MA50', 'MA200', 'RSI']).copy()
    if len(df_clean) < 500:
        return {"error": "历史数据不足，需要至少 500 个交易日的数据。"}
    
    # 存储所有匹配日期的索引
    match_dates = []
    
    # 循环扫描历史（从第 250 天开始，确保均线稳定）
    for i in range(250, len(df_clean) - max(lookforward_days)):
        row = df_clean.iloc[i]
        close = row['Close']
        ma50 = row['MA50']
        ma200 = row['MA200']
        rsi = row['RSI']
        
        # 计算该历史日期的分数（使用你现有的评分逻辑）
        # 注意：calculate_trend_score 需要 3 个参数
        trend_score = calculate_trend_score(close, ma50, ma200)
        
        # 计算动量分数需要 RSI 序列，但这里我们只有单个数值，用简易计算方式
        # 为了简化，这里用 RSI 的当前值作为动量分数基准（你也可以写更复杂的逻辑）
        # 但为了保持一致性，我们直接调用你现有的函数但传入临时 Series
        # 简单起见：把当前 RSI 当成分数基准，再取最近 6 天的变化
        if i >= 6:
            prev_rsi = df_clean.iloc[i-6]['RSI'] if i-6 >=0 else rsi
        else:
            prev_rsi = rsi
        rsi_change = rsi - prev_rsi
        momentum_score = min(100, max(0, round(rsi + rsi_change * 0.8)))
        
        # 检查是否匹配当前结构（允许误差 ±tolerance）
        if (abs(trend_score - current_trend_score) <= tolerance and 
            abs(momentum_score - current_momentum_score) <= tolerance):
            match_dates.append(i)
    
    if not match_dates:
        return {"error": "未找到足够相似的历史结构。"}
    
    # 统计每个未来周期的表现
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
            results[days] = {"error": "无有效数据"}
    
    return {
        "match_count": len(match_dates),
        "periods": results
    }

def get_market_state(close_price, ma50, ma200):
    """
    Single source of truth for structural state, shared by both the chart title
    and the message text to avoid contradictory labels.
    """
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
    """
    Momentum explanation only. Trend explanation now comes from get_market_state()
    so it always matches the actual price-vs-MA relationship shown on the chart.
    """
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
    """
    Retained for chart-title classification (kept simple/legacy for visuals).
    """
    if close_price <= ma200:
        return {
            "emoji": "🚨",
            "label": "Risk Warning",
        }
    if close_price < ma50:
        return {
            "emoji": "🟡",
            "label": "Pullback Buy Zone",
        }
    return {
        "emoji": "✅",
        "label": "Healthy Uptrend",
    }


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

        # ------------------ Pane 1: Price Structure Canvas ------------------
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

        # ------------------ Pane 2: RSI Relative Strength Subplot ------------------
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
        return (
            "⚠️ <b>ETF Trend Monitor</b>\n\n"
            "No valid ETF data was retrieved in this run."
        )

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

        # 👇 这一整块缩进 4 个空格，和 trend_score 平级
        historical = run_historical_analysis(
            df=df,
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
