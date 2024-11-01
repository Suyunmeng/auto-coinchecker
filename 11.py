import requests
import websocket
import json
import time
from datetime import datetime
from collections import defaultdict
import logging
import threading

# 设置币安API和WebSocket
BINANCE_REST_URL = "https://api.binance.com/api/v3/exchangeInfo"
BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
TELEGRAM_BOT_TOKEN = "7823461044:AAFQNoGfvI831LypnhM-iKPlBW_YlsLiMqc"
TELEGRAM_CHAT_ID = "6652055484"

# 全局变量
last_alert_time = defaultdict(lambda: None)
price_data = {}
trade_volume_data = {}
previous_minute_volume = defaultdict(lambda: 0)  # 用于存储前一分钟的成交量
one_hour_alert_count = defaultdict(int)
subscription_batches = []
price_change_24h_data = {}
ws = None

# 设置日志
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

# 获取所有USDT交易对
def fetch_usdt_symbols():
    try:
        response = requests.get(BINANCE_REST_URL)
        data = response.json()
        usdt_symbols = [symbol['symbol'].lower() for symbol in data['symbols'] if symbol['quoteAsset'] == 'USDT']
        # 将交易对分批，每批不超过5个
        for i in range(0, len(usdt_symbols), 5):
            subscription_batches.append(usdt_symbols[i:i + 5])
    except Exception as e:
        logging.error(f"获取USDT交易对列表出错: {e}")

# 发送Telegram消息
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logging.error(f"发送Telegram消息出错: {e}")

# 格式化提醒消息
def format_message(symbol, current_price, price_change_1m, volume_1m, major_side, major_volume, vol_24h, alert_count, change_interval, price_change_24h):
    alert_symbols = "💥" if alert_count > 6 else "⭐" * alert_count
    trend_icon = "📈" if price_change_1m > 0 else "📉"

    # 确保 change_interval 显示时间单位“秒”
    time_display = f"{change_interval}秒" if change_interval else "1分钟"

    message = (
        f"现货交易对提醒\n"
        f"${symbol.upper()} | #{symbol.upper()}_USDT |\n"
        f"Price: {current_price:.6f} ({price_change_24h:+.1f}% in 24h)\n"  # 添加24小时涨跌幅
        f"└{time_display} {'上涨' if price_change_1m > 0 else '下跌'}: {price_change_1m:+.1f}% {trend_icon}\n"
        f"{volume_1m:.2f} USDT traded in {time_display}\n"
        f"└{major_side}: {major_volume:.2f} USDT\n"
        f"24h Vol: {vol_24h:.2f} USDT\n"
        f"1小时预警数: {alert_count} {alert_symbols}"
    )

    # 成交量变动提醒
    if volume_change_percentage:
        message += f"\n成交量变化 {volume_change_percentage:.1f}%"

    return message

def fetch_24h_ticker_data():
    global price_change_24h_data
    try:
        response = requests.get("https://api.binance.com/api/v3/ticker/24hr")
        data = response.json()
        # 过滤出所有USDT交易对
        for ticker in data:
            symbol = ticker['symbol'].lower()
            if symbol.endswith("usdt"):
                price_change_24h_data[symbol] = float(ticker['priceChangePercent'])
        logging.info("24小时涨跌幅数据已更新")
    except Exception as e:
        logging.error(f"获取24小时涨跌幅数据出错: {e}")

# 定时更新24小时涨跌幅数据，每5分钟更新一次
def schedule_fetch_24h_ticker_data():
    while True:
        fetch_24h_ticker_data()
        time.sleep(300)  # 每5分钟更新一次

# 启动定时器线程
threading.Thread(target=schedule_fetch_24h_ticker_data, daemon=True).start()

# WebSocket消息处理
def on_message(ws, message):
    global last_alert_time, price_data, trade_volume_data, one_hour_alert_count, previous_minute_volume

    current_time = datetime.now()
    
    # 解析消息
    msg = json.loads(message)
    symbol = msg['s'].lower()
    current_price = float(msg['p'])
    price_change_24h = price_change_24h_data.get(symbol, 0)   # 24小时涨跌幅

    # 初始化数据
    if symbol not in price_data:
        price_data[symbol] = {
            "initial_price": current_price,
            "last_checked": time.time(),
            "alert_triggered": False,
        }
        trade_volume_data[symbol] = {
            "buy_volume": 0,
            "sell_volume": 0,
            "start_time": time.time(),
        }

        one_hour_alert_count[symbol] = {"count": 0, "last_reset_time": current_time}

    # 计算价格变化
    elapsed = time.time() - price_data[symbol]["last_checked"]
    price_change_1m = ((current_price - price_data[symbol]["initial_price"]) / price_data[symbol]["initial_price"]) * 100
    
    # 更新1分钟交易量
    if elapsed >= 60 or price_data[symbol]["alert_triggered"]:
        total_volume = trade_volume_data[symbol]["buy_volume"] + trade_volume_data[symbol]["sell_volume"]
        
        # 成交量变动检测
        previous_volume = previous_minute_volume[symbol]
        if previous_volume > 0 and (total_volume / previous_volume) >= 2:
            volume_change_percentage = (total_volume / previous_volume) * 100 - 100
            major_side = "流入 🔵" if trade_volume_data[symbol]["buy_volume"] > trade_volume_data[symbol]["sell_volume"] else "流出 🔴"
            major_volume = max(trade_volume_data[symbol]["buy_volume"], trade_volume_data[symbol]["sell_volume"])
            
            # 发送成交量变动提醒
            message = format_message(
                symbol=symbol,
                current_price=current_price,
                price_change_1m=price_change_1m,
                volume_1m=total_volume,
                major_side=major_side,
                major_volume=major_volume,
                alert_count=one_hour_alert_count[symbol]["count"],
                change_interval=None,
                volume_change_percentage=volume_change_percentage
            )
            send_telegram_message(message)
            logging.info(f"发送成交量变动提醒: {message}")

        # 保存本分钟成交量
        previous_minute_volume[symbol] = total_volume

        # 重置数据
        price_data[symbol]["initial_price"] = current_price
        price_data[symbol]["last_checked"] = time.time()
        trade_volume_data[symbol] = {
            "buy_volume": 0,
            "sell_volume": 0,
            "start_time": time.time(),
        }
    
    # 交易量更新
    if msg['m']:  # 如果是卖单
        trade_volume_data[symbol]["sell_volume"] += float(msg['q'])
    else:  # 如果是买单
        trade_volume_data[symbol]["buy_volume"] += float(msg['q'])
    
    # Debug输出
    logging.debug(f"{symbol.upper()} - 当前价格: {current_price}, 1分钟变化: {price_change_1m:.2f}%")
    logging.debug(f"{symbol.upper()} - 买入量: {trade_volume_data[symbol]['buy_volume']}, 卖出量: {trade_volume_data[symbol]['sell_volume']}")

# WebSocket连接
def on_open(ws):
    logging.info("WebSocket连接已打开")
    # 依次发送每个批次的订阅消息
    for batch in subscription_batches:
        subscribe_message = {
            "method": "SUBSCRIBE",
            "params": [f"{symbol}@trade" for symbol in batch],
            "id": 1
        }
        ws.send(json.dumps(subscribe_message))
        time.sleep(0.2)  # 每批次间隔200ms以避免超过消息限制

def on_ping(ws, message):
    ws.send(json.dumps({"pong": message}), opcode=websocket.ABNF.OPCODE_PONG)

def on_error(ws, error):
    logging.error(f"WebSocket连接出错: {error}")

def on_close(ws, close_status_code, close_msg):
    logging.info("WebSocket连接已关闭，尝试重连...")
    start_websocket()

def start_websocket():
    global ws
    ws = websocket.WebSocketApp(
        BINANCE_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_ping=on_ping,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever(ping_interval=150)

# 启动程序
if __name__ == "__main__":
    fetch_usdt_symbols()
    start_websocket()
