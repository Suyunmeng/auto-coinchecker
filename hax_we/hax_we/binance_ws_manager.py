# binance_ws_manager.py
import websocket
import requests
import json
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict
from config import BASE_URL, WS_BASE_URL, PING_INTERVAL, PING_TIMEOUT, RECONNECT_DELAY

class BinanceWebSocketManager:
    def __init__(self):
        self.symbols = []
        self.ws = None
        self.data = defaultdict(list)
        self.last_update = datetime.now()
    
    # 获取所有 USDT 交易对
    def fetch_symbols(self):
        response = requests.get(BASE_URL)
        if response.status_code == 200:
            data = response.json()
            self.symbols = [symbol['symbol'].lower() for symbol in data['symbols'] if symbol['quoteAsset'] == "USDT"]
            print(f"Fetched symbols: {self.symbols}")
        else:
            print("Error fetching symbols")

    # WebSocket 连接管理
    def start_websocket(self):
        self.fetch_symbols()  # 获取交易对
        stream = "/".join([f"{symbol}@aggTrade" for symbol in self.symbols])
        ws_url = f"{WS_BASE_URL}/stream?streams={stream}"
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.on_open = self.on_open
        self.ws.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)
    
    # WebSocket 事件处理
    def on_open(self, ws):
        print("WebSocket connection opened.")
    
    def on_message(self, ws, message):
        data = json.loads(message)
        stream = data.get("stream")
        payload = data.get("data")
        
        if payload:
            symbol = payload['s'].lower()
            trade_data = {
                "price": float(payload['p']),
                "quantity": float(payload['q']),
                "side": "buy" if payload['m'] else "sell",
                "timestamp": datetime.now()
            }
            self.data[symbol].append(trade_data)
            self.check_reset_data()
    
    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def on_close(self, ws):
        print("WebSocket connection closed. Reconnecting in", RECONNECT_DELAY, "seconds...")
        time.sleep(RECONNECT_DELAY)
        self.start_websocket()

    # 定时清理数据
    def check_reset_data(self):
        now = datetime.now()
        if (now - self.last_update) >= timedelta(minutes=1):
            self.data.clear()
            self.last_update = now
            print("Data reset for the new minute.")
