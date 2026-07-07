import os
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests

# 1. Securely read environment variables (without compromising privacy).
TELEGRAM_TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

def get_etf_data():
    print("Retrieving the latest historical data from Yahoo Finance...")
    # Capture data for one year plus 200 days to ensure extremely accurate MA200 calculations.
    etfs = {'CSPX.L': 'CSPX (iShares Core S&P 500)', 'QQQM': 'QQQM (Invesco NASDAQ 100)'}
    data_dict = {}
    
    for ticker, name in etfs.items():
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="2y") # extract data for 2 years to ensure a robust moving average.
        
        df = df.dropna(subset=['Close'])
        
        # Calculate MA50 and MA200
        df['MA50'] = df['Close'].rolling(window=50).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # Data from the most recent year is used for charting.
        df_recent = df.iloc[-252:]
        data_dict[ticker] = {"df": df_recent, "name": name}
        
    return data_dict

def generate_chart(data_dict):
    print("Generating a pure English internationalized dual moving average trend chart...")
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # Drawing CSPX
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

    # Drawing QQQM
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
    msg = "📊 **US Stock ETF Double Moving Average Long/Short Strategy Alert Board**\n\n"
    
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
            status_text = f"🚨【This triggers a bull market pullback signal for dollar-cost averaging!】\nThe current price has fallen below the 50-day moving average (MA50) but has held above the long-term 200-day moving average (MA200), placing it in a high-value "golden strike zone."！"
        elif close_price < ma200:
            status_text = f"💥【Highest level orange alert!】\nThe market has broken below the 200-day long-term bull/bear line, entering an absolute deep bear phase. It's advisable to lengthen the dollar-cost averaging cycle, invest in small batches to weather the winter, and never go all-in.！"
        else:
            status_text = f"✅【The overall market trend is good.】\nPrices are above all moving averages, the market is performing well, and we will continue to maintain our regular investment strategy."
            
        msg += f"• **{name}**\n"
        msg += f"{status_text}\n"
        msg += f"  - Latest closing price: {sign}{close_price:.2f} ({currency})\n"
        msg += f"  - MA50 medium-term line: {sign}{ma50:.2f} (Deviation: {dev50:.1f}%)\n"
        msg += f"  - MA200 death line: {sign}{ma200:.2f} (Deviation: {dev200:.1f}%)\n\n"
        
    return msg

def send_to_telegram(chart_path, text_msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Error: Environment variable TG_BOT_TOKEN or TG_CHAT_ID not detected. Please set it in the terminal!")
        return
        
    print("Securely pushed to mobile Telegram via a secure channel...")
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
        print("Telegram message push successfully！")
    else:
        print(f"Push notification failed, error code: {response.status_code}, reason: {response.text}")

if __name__ == "__main__":
    data = get_etf_data()
    path = generate_chart(data)
    message = build_message(data)
    send_to_telegram(path, message)
