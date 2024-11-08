# data_source.py
import websocket
import json
import threading
import time

class BinanceDataSource:
    def __init__(self, trading_pairs, on_message_callback):
        self.base_url = "wss://fstream.binance.com/stream?streams="
        self.trading_pairs = [f"{pair.lower()}@aggTrade" for pair in trading_pairs]
        self.on_message_callback = on_message_callback
        self.ws = None

    def connect(self):
        url = self.base_url + "/".join(self.trading_pairs)
        self.ws = websocket.WebSocketApp(url,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)
        threading.Thread(target=self.ws.run_forever).start()
        self.ping_pong()

    def on_message(self, ws, message):
        data = json.loads(message)
        if "data" in data:
            self.on_message_callback(data["data"])

    def on_error(self, ws, error):
        print("WebSocket error:", error)
        self.reconnect()

    def on_close(self, ws):
        print("WebSocket closed")
        self.reconnect()

    def reconnect(self):
        time.sleep(5)  # Reconnect after a short delay
        self.connect()

    def ping_pong(self):
        def send_ping():
            while True:
                self.ws.send("pong")
                time.sleep(180)  # Send pong every 3 minutes

        threading.Thread(target=send_ping).start()
