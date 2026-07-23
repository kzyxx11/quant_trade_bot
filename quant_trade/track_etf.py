import html
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests
import yfinance as yf

TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

# ============================================================
# NEW REPORT SYSTEM - CONFIGURATION & SCENE ENGINE
# ============================================================

# 场景判定阈值配置（量化）
SCENE_THRESHOLDS = {
    "trend": {
        "bull_min": 70,       # Trend >= 70 视为牛市
        "bear_max": 30,       # Trend <= 30 视为熊市
    },
    "momentum": {
        "healthy_min": 20,    # Momentum >= 20 视为正常
        "alert_threshold": 15, # 单日跌幅超过此值触发注意
        "buffer_zone": (19, 21),  # 防抖动缓冲带
    },
    "risk": {
        "low_max": 30,
        "moderate_max": 60,
        "high_min": 60,
    },
    "historical": {
        "rare_threshold": 30,   # Historical Match 样本数低于此值视为稀有
        "very_rare_threshold": 5, # 极端稀有
    }
}

# 场景判定状态机
SCENE_STATES = {
    "SCENE_1": {
        "name": "Normal Report",
        "title": "📊 ETF DAILY REPORT",
        "emoji": "🟢",
        "push_type": "silent",
    },
    "SCENE_2": {
        "name": "Market Update",
        "title": "⚠️ MARKET UPDATE",
        "emoji": "🟠",
        "push_type": "normal",
    },
    "SCENE_3": {
        "name": "Market Alert",
        "title": "🚨 MARKET ALERT",
        "emoji": "🔴",
        "push_type": "alert",
    },
    "SCENE_4": {
        "name": "Special Report",
        "title": "🚨 SPECIAL REPORT",
        "emoji": "🔴",
        "push_type": "alert",
    }
}

# 防抖动缓存（记录最近 N 次判定的结果）
_scene_history = []
_SCENE_HISTORY_MAX = 5  # 连续 5 次采样确认后才切换场景

def _determine_scene(trend_score, momentum_score, risk_level, match_count):
    """
    核心场景判定引擎，含防抖动逻辑。
    返回 scene_key (SCENE_1/2/3/4) 和判定依据。
    """
    global _scene_history
    
    # 1. 基础判定（基于当前数据）
    if match_count < SCENE_THRESHOLDS["historical"]["very_rare_threshold"]:
        raw_scene = "SCENE_4"
    elif match_count < SCENE_THRESHOLDS["historical"]["rare_threshold"]:
        raw_scene = "SCENE_3"
    elif (risk_level == "High" and 
          trend_score < SCENE_THRESHOLDS["trend"]["bull_min"]):
        raw_scene = "SCENE_3"
    elif (momentum_score < SCENE_THRESHOLDS["momentum"]["alert_threshold"] or
          risk_level == "Moderate"):
        raw_scene = "SCENE_2"
    else:
        raw_scene = "SCENE_1"
    
    # 2. 防抖动：缓冲带检查
    # 如果 Momentum 在缓冲带内，不轻易切换
    if (SCENE_THRESHOLDS["momentum"]["buffer_zone"][0] <= momentum_score <= 
        SCENE_THRESHOLDS["momentum"]["buffer_zone"][1]):
        # 如果有历史记录，保持上次场景，不切换
        if _scene_history:
            return _scene_history[-1], {"reason": "Buffer zone, holding previous scene"}
    
    # 3. 记录历史并判断是否达到切换阈值
    _scene_history.append(raw_scene)
    if len(_scene_history) > _SCENE_HISTORY_MAX:
        _scene_history.pop(0)
    
    # 统计最近 N 次中 raw_scene 的出现次数
    if len(_scene_history) >= _SCENE_HISTORY_MAX:
        counts = {}
        for s in _scene_history:
            counts[s] = counts.get(s, 0) + 1
        # 如果 raw_scene 出现次数 >= 3，切换
        if counts.get(raw_scene, 0) >= 3:
            return raw_scene, {"reason": f"Confirmed over {_SCENE_HISTORY_MAX} samples"}
        else:
            # 未达到切换阈值，返回上一个稳定场景
            return _scene_history[-2] if len(_scene_history) >= 2 else "SCENE_1", {"reason": "Not enough samples"}
    else:
        # 历史不足，返回当前判定结果
        return raw_scene, {"reason": "Initial判定"}

def escape_html(text):
    """安全转义 HTML 特殊字符"""
    if not text:
        return ""
    return html.escape(str(text))

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

def get_ai_summary(trend_score, momentum_score, risk_level):
    if trend_score >= 70 and momentum_score >= 50:
        return "The long-term trend remains healthy. Recent weakness appears to be a normal bull-market pullback. No portfolio adjustment is required."
    elif trend_score >= 70 and 30 <= momentum_score < 50:
        return "Trend is intact, but momentum is cooling. This is typical during consolidation phases. Maintain your existing strategy."
    elif trend_score >= 60 and momentum_score >= 40:
        return "Both trend and momentum are positive. The market is in a constructive phase. Continue regular investments."
    elif trend_score >= 60 and momentum_score < 30:
        return "Trend is still positive, but momentum is weakening. Watch for signs of a deeper correction."
    elif trend_score < 60 and momentum_score >= 50:
        return "Momentum is recovering but trend hasn't confirmed yet. Patience is advised."
    else:
        return "Market conditions are weak. Caution is recommended. Await clearer signals before adding exposure."

def get_daily_insight(action_type):
    if action_type == "buy":
        return "Current structure has historically been favorable for accumulation."
    elif action_type == "hold":
        return "Conditions are stable. Continue your regular DCA."
    elif action_type == "wait":
        return "Uncertainty is elevated. No immediate action required."
    else:
        return "Monitor key levels. No change to current strategy."

def build_monitor(close_price, ma200, momentum_score):
    items = []
    if close_price < ma200:
        items.append("⚠️ Price below MA200 (long-term support broken)")
    if momentum_score < 20:
        items.append("⚠️ Momentum extremely weak (< 20)")
    elif momentum_score < 30:
        items.append("Momentum is cooling (between 20-30)")
    if not items:
        items.append("No major signals at this time")
    # 返回不带星号的列表，用换行连接
    return "\n".join(items)

def build_scene_1_message(data, date_str, time_ago_str):
    """
    场景一：📊 ETF DAILY REPORT（正常市场，静默推送）
    符合所有新格式要求：英文、加粗、分隔线缩短、标签对齐、无星号、动态相对时间
    """
    # 1. 获取整体市场状态（取第一个资产作为代表）
    first_ticker = list(data.keys())[0]
    df_first = data[first_ticker]["df"]
    close_first = df_first["Close"].iloc[-1]
    ma50_first = df_first["MA50"].iloc[-1]
    ma200_first = df_first["MA200"].iloc[-1]
    trend_score_first = calculate_trend_score(close_first, ma50_first, ma200_first)
    
    if trend_score_first >= 70:
        market_status = "Bull Market"
        dca_status = "Normal (100%)"
        action_status = "Continue Investing"
        action_type = "buy"
    elif trend_score_first >= 50:
        market_status = "Constructive"
        dca_status = "Normal (100%)"
        action_status = "Continue Investing"
        action_type = "hold"
    else:
        market_status = "Correction / Bear Market"
        dca_status = "Reduce (50-75%)"
        action_status = "Stay Patient"
        action_type = "wait"
    
    # 2. 构建头部（使用 <b> 加粗，标签+值格式对齐）
    header = f"""
━━━━━━━━━━━━
📊 <b>ETF DAILY REPORT</b>
━━━━━━━━━━━━

🟢 <b>Market: {market_status}</b>
🟢 <b>Risk: Low</b>
💰 <b>DCA: {dca_status}</b>
📌 <b>Action: {action_status}</b>

━━━━━━━━━━━━

<b>🧠 AI Summary</b>

{get_ai_summary(trend_score_first, 50, "Low")}

"""
    # 3. 构建每个资产的区块
    asset_blocks = []
    for ticker, info in data.items():
        df = info["df"]
        close_price = df["Close"].iloc[-1]
        ma50 = df["MA50"].iloc[-1]
        ma200 = df["MA200"].iloc[-1]
        rsi = df["RSI"].iloc[-1]
        
        trend_score = calculate_trend_score(close_price, ma50, ma200)
        momentum_score = calculate_momentum_score(df["RSI"])
        historical = run_historical_analysis(
            df=info["df_full"],
            current_trend_score=trend_score,
            current_momentum_score=momentum_score
        )
        asset_name = escape_html(info["name"])
        symbol = escape_html(info["symbol"])
        
        # 颜色
        trend_color = "🟢" if trend_score >= 70 else ("🟠" if trend_score >= 50 else "🔴")
        momentum_color = "🟢" if momentum_score >= 50 else ("🟠" if momentum_score >= 30 else "🔴")
        
        # 历史统计
        if "error" not in historical:
            match_count = historical.get("match_count", 0)
            win_rate_90d = historical.get("periods", {}).get(90, {}).get("win_rate", 0)
            avg_return = historical.get("periods", {}).get(90, {}).get("avg_return", 0)
            max_dd = historical.get("periods", {}).get(90, {}).get("max_dd", 0)
            if match_count < SCENE_THRESHOLDS["historical"]["rare_threshold"]:
                match_text = f"<b>Historical Evidence</b>\n{match_count} similar cases (limited sample)\n90-Day Win Rate: {win_rate_90d:.1f}%\nAvg Return: {avg_return:+.1f}%\nMax Drawdown: {max_dd:.1f}%"
            else:
                match_text = f"<b>📚 Historical Match</b>\n(15-year historical comparison)\n\n• {match_count} similar cases\n• Win Rate: {win_rate_90d:.1f}%\n• Avg Return (90D): {avg_return:+.1f}%\n• Max Drawdown: {max_dd:.1f}%"
        else:
            match_text = "<b>📚 Historical Match</b>\nInsufficient data"
        # 组装单个资产块
        block = f"""━━━━━━━━━━━━
        
<b>📈 {asset_name}</b>

{trend_color} Trend: {trend_score}/100
{momentum_color} Momentum: {momentum_score}/100

<b>📊 Latest Price:</b> {symbol}{close_price:.2f}

MA50: {symbol}{ma50:.2f}
MA200: {symbol}{ma200:.2f}
RSI (14): {rsi:.1f}

{match_text}
"""
        asset_blocks.append(block)
    
    # 4. 构建底部（动态 Monitor 和 Daily Insight）
    monitor_text = build_monitor(close_first, ma200_first, 50)  # 用第一个资产的数据，实际可改进
    daily_insight = get_daily_insight(action_type)
    
    footer = f"""
━━━━━━━━━━━━

<b>⚠️ Monitor</b>
{monitor_text}

<b>💡 Daily Insight</b>
{daily_insight}

━━━━━━━━━━━━

📅 Data as of: {time_ago_str}
🤖 QuantTrackerBot

<i>This content is for informational purposes only. It does not constitute financial or investment advice.</i>
"""
    # 5. 组合完整消息
    full_message = header + "\n".join(asset_blocks) + footer
    
    # 6. 安全检查：如果消息超过 4096 字符，拆分
    if len(full_message) > 4096:
        first_part = header + asset_blocks[0] + "\n━━━━━━━━━━━━\n(Message continues in next part)"
        second_part = "\n".join(asset_blocks[1:]) + footer
        return [first_part, second_part]
    else:
        return [full_message]

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

def append_history(data, date_str):
    """
    把当天每个资产的核心指标追加到 history.csv
    """
    history_path = Path("docs/history.csv")
    
    # 如果文件不存在，创建表头
    if not history_path.exists():
        with open(history_path, "w") as f:
            f.write("date,ticker,close,trend_score,momentum_score,match_count,win_rate_90d\n")
    
    # 准备新行
    lines = []
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
        
        match_count = historical.get("match_count", 0)
        win_rate = historical.get("periods", {}).get(90, {}).get("win_rate", 0)
        
        # 读取现有的历史数据，检查今天是否已经记录过
        import pandas as pd
        existing = pd.read_csv(history_path) if history_path.exists() else pd.DataFrame()
        
        # 如果今天已有记录，跳过
        if not existing.empty and len(existing[existing["date"] == date_str]) > 0:
            print(f"[History] Data for {date_str} already exists, skipping append.")
            return
        
        lines.append(f"{date_str},{ticker},{close_price:.2f},{trend_score},{momentum_score},{match_count},{win_rate:.1f}")
    
    # 追加到文件
    if lines:
        with open(history_path, "a") as f:
            for line in lines:
                f.write(line + "\n")
        print(f"[History] Appended {len(lines)} records to history.csv")

def generate_trend_chart():
    """
    读取 history.csv，为每个资产生成独立的趋势图，保存为 docs/trend_{ticker}.png
    """
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    
    history_path = Path("docs/history.csv")
    if not history_path.exists():
        print("[History] No history data found, skipping trend chart.")
        return
    
    df = pd.read_csv(history_path)
    df["date"] = pd.to_datetime(df["date"])
    
    tickers = df["ticker"].unique()
    
    for ticker in tickers:
        ticker_df = df[df["ticker"] == ticker].sort_values("date")
        ticker_df = ticker_df.tail(30)  # 只显示最近30天
        
        fig, ax = plt.subplots(figsize=(10, 3))
        ax.plot(ticker_df["date"], ticker_df["trend_score"], color="#58a6ff", linewidth=2, label="Trend Score")
        ax.axhline(y=50, color="#8b949e", linestyle="--", linewidth=0.8, alpha=0.5)
        ax.set_title(f"{ticker} - Trend Score Over Time", fontsize=10, color="#e6edf3")
        ax.set_ylabel("Trend Score", color="#8b949e")
        ax.set_ylim(0, 110)
        ax.set_autoscale_on(False)
        ax.grid(True, alpha=0.1, color="#30363d")
        ax.legend(loc="lower left")
        
        # 在图表右上角固定位置显示最新分数（不随数据点移动）
        if not ticker_df.empty:
            last_score = ticker_df.iloc[-1]["trend_score"]
            ax.text(0.98, 0.98, f"Current: {last_score:.0f}", 
                    transform=ax.transAxes,
                    color="#58a6ff", fontsize=11, fontweight="bold",
                    verticalalignment='top', horizontalalignment='right')
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        plt.tight_layout()
        chart_path = Path(f"docs/trend_{ticker}.png")
        plt.savefig(chart_path, dpi=150, facecolor='#0d1117', edgecolor='none')
        plt.close()
        print(f"[History] Trend chart saved to {chart_path}")
    return chart_path

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
        <img src="trend_{ticker}.png" alt="Trend Score History" style="width:100%; max-width:900px; border-radius:8px; margin-bottom:20px; border:1px solid #30363d;">
        <div class="row"><span class="label">Latest Close</span><span class="value">{info['symbol']}{close_price:.2f}</span></div>
        <div class="row"><span class="label">Trend Score</span><span class="value">{trend_score}/100</span></div>
        <div class="row"><span class="label">Momentum Score</span><span class="value">{momentum_score}/100</span></div>
        <div class="row"><span class="label">Historical Match</span><span class="value">{historical.get('match_count', 'N/A')} occurrences</span></div>
        <div class="row"><span class="label">90-day Win Rate</span><span class="value">{historical.get('periods', {}).get(90, {}).get('win_rate', 'N/A')}%</span></div>
        <div class="row"><span class="label">Suggested Action</span><span class="value"><span class="badge {badge_class}">{action_text}</span></span></div>
    </div>
"""

    html_template += """
    <div class="footer">
        Updated: {date} · <a href="https://t.me/ETF_Trend_Monitor" target="_blank">Telegram Channel</a> · <a href="https://github.com/kzyxx11/quant_trade_bot" target="_blank">GitHub</a>
    </div>
</body>
</html>
"""
    html_template = html_template.replace("{date}", date_str)
    html_template = html_template.replace("(date)", date_str)  
    return html_template
    
def main():
    data = fetch_etf_data()
    if not data:
        print("No data fetched. Exiting.")
        return

    tz_gmt8 = timezone(timedelta(hours=8))
    now = datetime.now(tz_gmt8)
    today_str = now.strftime("%Y-%m-%d")
    append_history(data, today_str)
    
    generate_trend_chart()
    chart_path = generate_chart(data)
    
    # 计算相对时间
    run_timestamp = now

    # 这里我们将运行时间戳保存，后面生成消息时计算差值
    # 为了简单，我们直接将当前时间作为相对基准，但实际应该用同一个时间
    display_date = now.strftime("%Y-%m-%d %H:%M")  # 保留旧格式备用
    
    # 生成相对时间字符串（Just now / X min ago）
    # 这里我们假设从脚本开始到发送消息时间很短，所以直接设为 "Just now"
    # 但如果你希望更精确，可以记录 start_time
    time_ago = "Just now"  # 后续可改为真实差值

    # 生成场景一消息
    messages = build_scene_1_message(data, display_date, time_ago)
    for idx, msg in enumerate(messages):
        if idx == 0:
            send_to_telegram(chart_path, msg)
        else:
            send_to_telegram(None, msg)

    # 网页看板生成（不变）
    today_str_full = now.strftime("%Y-%m-%d %H:%M (GMT+8)")
    html_content = generate_html(data, today_str_full)
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    index_path = docs_dir / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[Success] Dashboard updated at {index_path}")

if __name__ == "__main__":
    main()
