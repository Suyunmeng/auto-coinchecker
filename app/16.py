import websocket
import requests
import json
import time
import threading
import signal
from datetime import datetime, timedelta
from collections import defaultdict

# Telegram configuration (replace with actual token and chat ID)
TELEGRAM_TOKEN = "7722623966:AAEoL-zfPkT6tAjONUTSQcK1qP1V7H76aJI"
TELEGRAM_CHAT_ID = "6652055484"

BASE_URL = "https://fapi.binance.com"
WEBSOCKET_URL = "wss://fstream.binance.com"
STREAM_LIMIT = 200
FLUCTUATION_THRESHOLD_1M = 0.005  # ±0.5%
FLUCTUATION_THRESHOLD_1H = 0.02  # ±2%
VOLUME_THRESHOLD = 30000  # 30,000 USDT


class BinanceMonitor:
    def __init__(self):
        self.symbols = []
        self.last_prices = {}
        self.hourly_baseline = {}
        self.alert_count_1h = defaultdict(int)
        self.alert_triggered_1h = set()
        self.ws = None
        self.stop_event = threading.Event()
        self.connect_to_websocket()
        self.last_alert_time = {}
        self.last_alert_price = {}

    def fetch_symbols(self):
        url = f"{BASE_URL}/fapi/v1/exchangeInfo"
        response = requests.get(url)
        self.symbols = [symbol['symbol'] for symbol in response.json()['symbols'] if symbol['quoteAsset'] == 'USDT']
        self.reset_baseline_prices()

    def reset_baseline_prices(self):
        for symbol in self.symbols:
            self.hourly_baseline[symbol] = None
            self.alert_triggered_1h.discard(symbol)
            self.alert_count_1h[symbol] = 0

    def connect_to_websocket(self):
        self.fetch_symbols()
        streams = [f"{symbol.lower()}@aggTrade/{symbol.lower()}@miniTicker" for symbol in self.symbols]
        streams_url = f"{WEBSOCKET_URL}/stream?streams={'/'.join(streams[:STREAM_LIMIT])}"
        
        def on_open(ws):
            print("WebSocket connection opened.")
        
        def on_close(ws, *args):
            print("WebSocket connection closed. Reconnecting...")
            self.connect_to_websocket()

        def on_message(ws, message):
            data = json.loads(message)
            if "data" in data:
                event = data["data"]
                if event["e"] == "aggTrade":
                    self.process_trade(event)
                elif event["e"] == "24hrMiniTicker":
                    self.update_24hr_change(event)

        def on_error(ws, error):
            print(f"Error: {error}. Restarting WebSocket...")
            ws.close()
        
        self.ws = websocket.WebSocketApp(streams_url, on_open=on_open, on_close=on_close, on_message=on_message, on_error=on_error)
        wst = threading.Thread(target=self.ws.run_forever)
        wst.start()
        
    def process_trade(self, trade,side_volume):
        symbol = trade["s"]
        price = float(trade["p"])
        quantity = float(trade["q"])
        trade_time = datetime.utcfromtimestamp(trade["T"] / 1000)
        
        self.check_1m_fluctuation(symbol, price, trade_time)
        
        if symbol not in self.last_prices:
            self.last_prices[symbol] = price
        else:
            self.last_prices[symbol] = price

        # 计算买方和卖方的成交量
        buy_volume = sum([trade['quoteQty'] for trade in trades if not trade['isBuyerMaker']])
        sell_volume = sum([trade['quoteQty'] for trade in trades if trade['isBuyerMaker']])

        # 判断买方或卖方哪个成交量更大，作为 side_volume 和 flow_direction
        if buy_volume > sell_volume:
            side_volume = buy_volume
            flow_direction = '🟢 流入'
        else:
            side_volume = sell_volume
            flow_direction = '🔴 流出'

        # 计算流入/流出的占比
        side_percentage = (side_volume / (buy_volume + sell_volume)) * 100

    def update_24hr_change(self, ticker):
        symbol = ticker["s"]
        close_price = float(ticker["c"])
        open_price_24h = float(ticker["o"])
        percent_change_24h = ((close_price - open_price_24h) / open_price_24h) * 100
        self.last_prices[symbol] = close_price
        
        if self.hourly_baseline[symbol] is None:
            self.hourly_baseline[symbol] = close_price
        self.check_1h_fluctuation(symbol, close_price)

    def check_1m_fluctuation(self, symbol, current_price, trade_time, side_volume):
        """
        检查 1 分钟内的价格波动和成交量条件，包含连续触发逻辑。
        """
        self.debug_output()
        if symbol in self.last_prices:
            last_price = self.last_prices[symbol]
            price_change = (current_price - last_price) / last_price * 100
            inflow_outflow_volume = max(side_volume['buy'], side_volume['sell'])
    
            # 首次满足条件时触发提醒
            if abs(price_change) >= 0.5 and inflow_outflow_volume >= 30000:
                if symbol not in self.last_alert_time or (trade_time - self.last_alert_time[symbol]).total_seconds() >= 60:
                    self.send_telegram_alert(symbol, current_price, price_change, inflow_outflow_volume, trade_time, "1 min")
                    self.last_alert_time[symbol] = trade_time
                    self.last_alert_price[symbol] = current_price
                else:
                    # 若在 1 分钟内，再次满足条件，调用连续触发检查
                    self.check_continuous_trigger(symbol, current_price, trade_time, side_volume)
            def debug_output(self):
                """
                输出调试信息：当前监控的交易对列表、每个交易对的最新价格和成交量数据。
                """
                print("当前监控的交易对列表及状态：")
                for symbol in self.last_prices:
                    print(f"交易对: {symbol}")
                    print(f"  最新价格: {self.last_prices[symbol]}")
                    print(f"  当前成交量 (USDT): {self.current_volumes[symbol]['total']}")

    def check_continuous_trigger(self, symbol, current_price, trade_time, side_volume):
        """
        检查连续触发条件：若在 1 分钟内再次满足条件，则触发新提醒。
        """
        if symbol in self.last_alert_time:
            # 计算与上次提醒的时间差
            time_diff = (trade_time - self.last_alert_time[symbol]).total_seconds()
            last_price = self.last_alert_price[symbol]
            price_change = (current_price - last_price) / last_price * 100
            inflow_outflow_volume = max(side_volume['buy'], side_volume['sell'])
    
            # 若满足条件 2.2 的连续触发规则
            if abs(price_change) >= 0.5 and inflow_outflow_volume >= 30000:
                # 判断是否在 1 分钟内再次触发
                time_interval = f"{int(time_diff)} 秒" if time_diff < 60 else "1 min"
                self.send_telegram_alert(symbol, current_price, price_change, inflow_outflow_volume, trade_time, time_interval)
                
                # 记录新的触发时间和价格，防止重复提醒
                self.last_alert_time[symbol] = trade_time
                self.last_alert_price[symbol] = current_price
    def debug_output(self):
        """
        输出调试信息：当前监控的交易对列表、每个交易对的最新价格和成交量数据。
        """
        print("当前监控的交易对列表及状态：")
        for symbol in self.last_prices:
            print(f"交易对: {symbol}")
            print(f"  最新价格: {self.last_prices[symbol]}")
            print(f"  当前成交量 (USDT): {self.current_volumes[symbol]['total']}")

    def check_1h_fluctuation(self, symbol, current_price):
        if symbol in self.hourly_baseline and self.hourly_baseline[symbol] is not None:
            baseline_price = self.hourly_baseline[symbol]
            price_change = (current_price - baseline_price) / baseline_price
            if abs(price_change) >= FLUCTUATION_THRESHOLD_1H and symbol not in self.alert_triggered_1h:
                volume = current_price * VOLUME_THRESHOLD  # Simplified for example
                self.send_telegram_alert(symbol, current_price, price_change, volume, datetime.utcnow(), "1h")
                self.alert_triggered_1h.add(symbol)
                self.alert_count_1h[symbol] += 1

    def send_telegram_alert(self, symbol, price, price_change, volume, time, interval_type, side_volume, side_percentage):
        change_dir = "📈" if price_change > 0 else "📉"
        change_text = f"{'+' if price_change > 0 else ''}{price_change * 100:.2f}% {change_dir}"
        message = (
            f"${symbol} | #{symbol}\n"
            f"Price: {price:.4f}\n"
            f"└ {interval_type} change: {change_text}\n"
            f"{volume:.2f} USDT traded in {interval_type}\n"
            f"└ {flow_direction}: {side_volume:.2f} USDT [{side_percentage:.1f}%]\n"
            f"24h Vol: {volume * 24:.2f} USDT\n"
            f"1-hour Alert Count: {self.alert_count_1h[symbol]} {'🌟' * self.alert_count_1h[symbol]}{'💥' if self.alert_count_1h[symbol] >= 4 else ''}"
        )
        self.send_telegram_message(message)

    def send_telegram_message(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            requests.post(url, data=data)
        except requests.RequestException as e:
            print(f"Failed to send Telegram message: {e}")

    def start(self):
        signal.signal(signal.SIGINT, self.stop)
        while not self.stop_event.is_set():
            time.sleep(1)

    def stop(self, *args):
        print("Stopping Binance monitor...")
        self.stop_event.set()
        if self.ws:
            self.ws.close()

if __name__ == "__main__":
    monitor = BinanceMonitor()
    monitor.start()
