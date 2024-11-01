import json
import requests
import time
import threading
import websocket
from collections import defaultdict

# Telegram配置
TELEGRAM_BOT_TOKEN = "7722623966:AAEoL-zfPkT6tAjONUTSQcK1qP1V7H76aJI"
TELEGRAM_CHAT_ID = "6652055484"

# API与连接配置
BINANCE_WS_URL = "wss://fstream.binance.com/ws/"
BINANCE_CONTRACT_API = "https://fapi.binance.com/fapi/v1/exchangeInfo"
SUBSCRIBE_BATCH_SIZE = 200
PERCENT_CHANGE_1_MIN = 0.5 / 100
PERCENT_CHANGE_1_HOUR = 2.0 / 100
VOLUME_THRESHOLD = 30000

# 数据存储结构
price_data = defaultdict(lambda: {'last_price': 0, 'volume': 0, 'hourly_base': 0, 'alerts': 0, 'alert_time': 0})
trade_data = defaultdict(list)


# Telegram提醒
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Telegram message failed: {response.text}")


# 获取所有USDT合约交易对
def fetch_usdt_pairs():
    response = requests.get(BINANCE_CONTRACT_API)
    data = response.json()
    return [s["symbol"] for s in data["symbols"] if s["quoteAsset"] == "USDT"]


# WebSocket on_message回调处理函数
def on_message(ws, message):
    data = json.loads(message)
    event_type = data.get("e")
    symbol = data.get("s")
    
    if event_type == "aggTrade":
        handle_agg_trade(data)
    elif event_type == "24hrMiniTicker":
        handle_mini_ticker(data)


# 实时交易数据处理
def handle_agg_trade(data):
    symbol = data["s"]
    price = float(data["p"])
    quantity = float(data["q"])
    is_buyer_maker = data["m"]
    usdt_volume = price * quantity

    current_time = time.time()
    price_data[symbol]["last_price"] = price
    price_data[symbol]["volume"] += usdt_volume
    trade_data[symbol].append((current_time, price, usdt_volume, is_buyer_maker))

    # Debug输出
    print(f"[DEBUG] aggTrade for {symbol}: Price={price}, Volume={usdt_volume}, Buyer={not is_buyer_maker}")

    check_price_volume_alert(symbol)


# miniTicker数据处理
def handle_mini_ticker(data):
    symbol = data["s"]
    last_price = float(data["c"])
    open_price = float(data["o"])
    high_price = float(data["h"])
    low_price = float(data["l"])
    volume_24h = float(data["v"])
    turnover_24h = float(data["q"])

    price_change_percent = (last_price - open_price) / open_price * 100
    price_data[symbol].update({
        "last_price": last_price,
        "24h_change": price_change_percent,
        "24h_volume": turnover_24h,
        "24h_high": high_price,
        "24h_low": low_price
    })

    # Debug输出
    print(f"[DEBUG] miniTicker for {symbol}: Last Price={last_price}, 24h Change={price_change_percent:.2f}%, "
          f"24h Vol={turnover_24h} USDT")


# 条件检查与提醒发送
def check_price_volume_alert(symbol):
    data = price_data[symbol]
    last_price = data["last_price"]
    volume = data["volume"]
    current_time = time.time()

    trades_in_last_min = [(t, p, v, m) for t, p, v, m in trade_data[symbol] if current_time - t <= 60]
    if not trades_in_last_min:
        return

    initial_price = trades_in_last_min[0][1]
    percent_change = (last_price - initial_price) / initial_price

    # 检查是否符合触发条件，先检测是否在“提醒后的1分钟监控状态”中
    alert_interval = current_time - data["alert_time"]
    if alert_interval <= 60 or alert_interval > 120:
        if abs(percent_change) >= PERCENT_CHANGE_1_MIN and volume > VOLUME_THRESHOLD:
            data["alert_time"] = current_time  # 记录提醒时间
            update_hourly_alert_count(symbol)
            send_price_volume_alert(symbol, last_price, percent_change, volume, trades_in_last_min)


# 更新每小时的预警数
def update_hourly_alert_count(symbol):
    data = price_data[symbol]
    data["alerts"] += 1
    if data["alerts"] < 4:
        alert_icon = "🌟" * data["alerts"]
    else:
        alert_icon = "💥"
    data["alert_icon"] = alert_icon


# Telegram提醒格式
def send_price_volume_alert(symbol, price, change, volume, trades):
    is_buyer_maker_count = sum(1 for _, _, _, m in trades if not m)
    total_trades = len(trades)
    inflow_outflow = "流入" if is_buyer_maker_count > total_trades / 2 else "流出"
    inflow_outflow_icon = "🟢" if inflow_outflow == "流入" else "🔴"

    time_since_last_alert = int(time.time() % 60)  # 记录从上次提醒的时间间隔
    time_display = f"{time_since_last_alert}秒" if time_since_last_alert < 60 else "1 min"

    message = f"""
$ {symbol} | #{symbol}_USDT
Price: {price:.4f} ({price_data[symbol]['24h_change']:.2f}% in 24h)
└ {time_display} change: {change * 100:.2f}% {'📈' if change > 0 else '📉'}
{volume:.2f} USDT traded in {time_display}
└ {inflow_outflow}: {volume:.2f} USDT [{inflow_outflow_icon}]
24h Vol: {price_data[symbol]['24h_volume']:.2f} USDT
1小时预警数: {price_data[symbol]['alerts']} {price_data[symbol].get('alert_icon', '')}
    """
    
    print(f"[DEBUG] Sending Telegram alert for {symbol}: {message}")
    send_telegram_message(message)


# WebSocket连接与重连管理
def start_ws_connection():
    usdt_pairs = fetch_usdt_pairs()
    streams = [
        f"{pair.lower()}@aggTrade" for pair in usdt_pairs
    ] + [f"{pair.lower()}@miniTicker" for pair in usdt_pairs]
    ws_url = BINANCE_WS_URL + '/'.join(streams)

    ws = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=lambda ws, err: print(f"WebSocket error: {err}"),
        on_close=lambda ws: print("WebSocket closed, reconnecting...") or start_ws_connection()
    )
    ws.run_forever()


# 1小时涨跌幅监控
def hourly_change_monitor():
    while True:
        current_hour = int(time.time() // 3600)
        
        for symbol, data in price_data.items():
            if current_hour != data["hourly_base"]:
                data["hourly_base"] = current_hour
                data["hourly_price"] = data["last_price"]
            else:
                price_change = (data["last_price"] - data["hourly_price"]) / data["hourly_price"]
                if abs(price_change) >= PERCENT_CHANGE_1_HOUR:
                    send_hourly_alert(symbol, price_change)

        time.sleep(60)


# 1小时涨跌幅提醒
def send_hourly_alert(symbol, price_change):
    time_since_hour_start = int(time.time() % 3600 // 60)
    message = f"""
$ {symbol} | #{symbol}_USDT
Price: {price_data[symbol]["last_price"]:.4f} ({price_data[symbol]["24h_change"]:.2f}% in 24h)
└ {time_since_hour_start} min change: {price_change * 100:.2f}% {'📈' if price_change > 0 else '📉'}
1小时预警数: {price_data[symbol]["alerts"]} {price_data[symbol].get('alert_icon', '')}
    """
    print(f"[DEBUG] Sending hourly alert for {symbol}: {message}")
    send_telegram_message(message)


# 主线程启动
if __name__ == "__main__":
    threading.Thread(target=start_ws_connection).start()
    threading.Thread(target=hourly_change_monitor).start()
