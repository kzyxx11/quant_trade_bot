import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests

# 1. 安全读取环境变量（绝不泄露隐私）
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

def get_etf_data():
    print("正在从雅虎金融提取最新历史数据...")
    # 抓取 1 年加 200 天的数据，确保 MA200 计算极其精准
    etfs = {'CSPX.L': 'CSPX (iShares Core S&P 500)', 'QQQM': 'QQQM (Invesco NASDAQ 100)'}
    data_dict = {}
    
    for ticker, name in etfs.items():
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="2y") # 抓取2年确保均线饱满
        
        # 【核心修复】先将因时差/清算导致的末尾 NaN 行彻底剔除，确保拿到的是真实的最新收盘日
        df = df.dropna(subset=['Close'])
        
        # 计算 MA50 和 MA200
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # 截取最近一年的数据用于画图展示
        df_recent = df.iloc[-252:]
        data_dict[ticker] = {"df": df_recent, "name": name}
        
    return data_dict

def generate_chart(data_dict):
    print("正在生成纯英文国际化双均线趋势图表...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 绘制 CSPX
    cspx_data = data_dict['CSPX.L']['df']
    ax1.plot(cspx_data.index, cspx_data['Close'], color='#1e6091', linewidth=2, label='Price')
    ax1.plot(cspx_data.index, cspx_data['MA50'], color='#52b788', linestyle='--', label='MA50 (Mid-term)')
    ax1.plot(cspx_data.index, cspx_data['MA200'], color='#b7094c', linestyle='-', linewidth=2, label='MA200 (Long-term)')
    ax1.fill_between(cspx_data.index, cspx_data['Close'], color='#1e6091', alpha=0.05)
    ax1.set_title(data_dict['CSPX.L']['name'], fontsize=12, loc='left', weight='bold')
    ax1.set_ylabel("Price (GBP)")
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='upper left')
    ax1.text(cspx_data.index[-1], cspx_data['Close'].iloc[-1], f" £{cspx_data['Close'].iloc[-1]:.2f}", color='#1e6091', weight='bold')

    # 绘制 QQQM
    qqqm_data = data_dict['QQQM']['df']
    ax2.plot(qqqm_data.index, qqqm_data['Close'], color='#d90429', linewidth=2, label='Price')
    ax2.plot(qqqm_data.index, qqqm_data['MA50'], color='#52b788', linestyle='--', label='MA50 (Mid-term)')
    ax2.plot(qqqm_data.index, qqqm_data['MA200'], color='#b7094c', linestyle='-', linewidth=2, label='MA200 (Long-term)')
    ax2.fill_between(qqqm_data.index, qqqm_data['Close'], color='#d90429', alpha=0.05)
    ax2.set_title(data_dict['QQQM']['name'], fontsize=12, loc='left', weight='bold')
    ax2.set_ylabel("Price (USD)")
    ax2.set_xlabel("Date")
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='upper left')
    ax2.text(qqqm_data.index[-1], qqqm_data['Close'].iloc[-1], f" ${qqqm_data['Close'].iloc[-1]:.2f}", color='#d90429', weight='bold')

    plt.suptitle("ETF Strategy Monitor: MA50 & MA200 Trend Filter", fontsize=14, weight='bold')
    plt.tight_layout()
    
    chart_path = "etf_trend.png"
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return chart_path

def build_message(data_dict):
    msg = "📊 **美股 ETF 双均线多空策略警报看板**\n\n"
    
    for ticker, info in data_dict.items():
        df = info['df']
        name = info['name']
        
        close_price = df['Close'].iloc[-1]
        ma50 = df['MA50'].iloc[-1]
        ma200 = df['MA200'].iloc[-1]
        
        dev50 = ((close_price - ma50) / ma50) * 100
        dev200 = ((close_price - ma200) / ma200) * 100
        
        currency = "GBP" if "CSPX" in ticker else "USD"
        sign = "£" if "CSPX" in ticker else "$"
        
        # 核心策略三象限判断
        if close_price < ma50 and close_price > ma200:
            status_text = f"🚨【触发定投牛市回踩信号！】\n当前价格跌破 MA50，但守住了 MA200 长期生死线，属于高性价比【黄金击球区】！"
        elif close_price < ma200:
            status_text = f"💥【最高级别橙色防御警报！】\n市场已跌破 200 日长期生死线，进入绝对深熊阶段。建议拉长定投周期，分批小额过冬，切勿梭哈！"
        else:
            status_text = f"✅【大盘趋势良好】\n价格处于所有均线之上，市场运行良好，继续保持常规纪律定投。"
            
        msg += f"• **{name}**\n"
        msg += f"{status_text}\n"
        msg += f"  - 最新收盘价: {sign}{close_price:.2f} ({currency})\n"
        msg += f"  - MA50 中期线: {sign}{ma50:.2f} (偏离度: {dev50:.1f}%)\n"
        msg += f"  - MA200 生死线: {sign}{ma200:.2f} (偏离度: {dev200:.1f}%)\n\n"
        
    return msg

def send_to_telegram(chart_path, text_msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("错误：未检测到环境变量 TG_BOT_TOKEN 或 TG_CHAT_ID，请在终端设置！")
        return
        
    print("正在通过安全通道安全推送至手机 Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    
    with open(chart_path, 'rb') as photo:
        payload = {
            'chat_id': CHAT_ID,
            'caption': text_msg,
            'parse_mode': 'Markdown'
        }
        files = {'photo': photo}
        response = requests.post(url, data=payload, files=files)
        
    if response.status_code == 200:
        print("Telegram 消息安全推送成功！")
    else:
        print(f"推送失败，错误码: {response.status_code}, 原因: {response.text}")

if __name__ == "__main__":
    data = get_etf_data()
    path = generate_chart(data)
    message = build_message(data)
    send_to_telegram(path, message)
