import time
import json
import requests
import websocket
from datetime import datetime
from threading import Thread, Event

# Telegram 配置
TELEGRAM_TOKEN = "7823461044:AAFQNoGfvI831LypnhM-iKPlBW_YlsLiMqc"
CHAT_ID = "6652055484"

# Debug模式开关
DEBUG_MODE = True

# 全局变量存储成交量数据
current_volumes = {}
previous_volumes = {}
reconnect_event = Event()

# 打印Debug信息的函数
def debug_print(message):
    if DEBUG_MODE:
        print(f"[DEBUG {datetime.now()}] {message}")

# 发送 Telegram 消息
def send_telegram_message(message):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(telegram_url, data=payload)
    if response.status_code != 200:
        debug_print(f"发送 Telegram 消息失败: {response.text}")
    else:
        debug_print("发送 Telegram 消息成功")

# WebSocket 收到消息时的处理
def on_message(ws, message):
    data = json.loads(message)
    if 'ping' in data:
        ws.send(json.dumps({'pong': data['ping']}))
        debug_print("收到 Ping 并回复 Pong")
    elif 'stream' in data and data['stream'].endswith('@aggTrade'):
        symbol = data['data']['s']
        volume = float(data['data']['q'])

        if symbol.endswith("USDT"):
            if symbol not in current_volumes:
                current_volumes[symbol] = 0
            current_volumes[symbol] += volume
            debug_print(f"更新当前成交量: {symbol} -> {current_volumes[symbol]}")

# 每分钟检查一次成交量变化
def monitor():
    global current_volumes, previous_volumes
    while True:
        time.sleep(60)
        debug_print("开始新的成交量监控周期")
        for symbol, volume in current_volumes.items():
            previous_volume = previous_volumes.get(symbol, 0)
            if previous_volume > 0:
                change_percentage = (volume / previous_volume - 1) * 100
                if change_percentage > 200:
                    flow_direction = "流入" if volume > previous_volume else "流出"
                    message = (f"*#{symbol}* 大额{flow_direction}，价格上浮\n"
                               f"成交量真实变化：{change_percentage:.1f}% （超过200%阈值）\n"
                               f"当前成交量: {volume:.4f}")
                    send_telegram_message(message)
                    debug_print(f"发送提醒消息: {message}")

            previous_volumes[symbol] = volume
        current_volumes = {}
        debug_print("重置当前分钟的成交量数据")

# WebSocket 打开时的处理
def on_open(ws):
    debug_print("WebSocket 连接已打开，订阅所有现货 USDT 交易对")
    subscribe_message = {
        "method": "SUBSCRIBE",
        "params": ["!aggTrade@arr"],
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))

# WebSocket 关闭时的处理
def on_close(ws, close_status_code, close_msg):
    debug_print(f"WebSocket 连接已关闭，状态码: {close_status_code}, 信息: {close_msg}")
    reconnect_event.set()

# WebSocket 发生错误时的处理
def on_error(ws, error):
    debug_print(f"WebSocket 错误: {error}")
    reconnect_event.set()

# WebSocket 连接和重连处理
def connect_websocket():
    while True:
        reconnect_event.clear()
        ws = websocket.WebSocketApp(
            "wss://stream.binance.com:9443/stream?streams=!aggTrade@arr",
            on_open=on_open,
            on_message=on_message,
            on_close=on_close,
            on_error=on_error
        )
        ws.run_forever()
        reconnect_event.wait()
        debug_print("等待重连")

# 启动监控线程
if __name__ == "__main__":
    websocket_thread = Thread(target=connect_websocket)
    websocket_thread.start()

    monitor_thread = Thread(target=monitor)
    monitor_thread.start()
