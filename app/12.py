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

BINANCE_WS_BASE_URL = "wss://fstream.binance.com/stream?streams="
BINANCE_CONTRACT_API = "https://fapi.binance.com/fapi/v1/exchangeInfo"
STREAM_LIMIT = 190
RECONNECT_DELAY = 5  # 初始重连延迟时间（秒）
FLUCTUATION_THRESHOLD_1M = 0.005  # ±0.5%
FLUCTUATION_THRESHOLD_1H = 0.02  # ±2%
VOLUME_THRESHOLD = 30000  # 30,000 USDT

class BinanceMonitor:
    def __init__(self):
        # Initialization remains unchange
        self.symbols = self.fetch_usdt_pairs()
        self.hourly_baseline = {}
        self.alert_triggered_1h = set()
        self.alert_count_1h = defaultdict(int)
        self.last_prices = {}
        self.current_minute = datetime.utcnow().minute
        self.volume_data = defaultdict(lambda: {"buy": 0, "sell": 0})
        self.triggered_time_1m = {}  # Tracks last triggered time for 1-minute alerts
        self.triggered_price_1m = {}  # Tracks last triggered price for 1-minute alerts
        self.vol_24h = defaultdict(float)
        self.ws = None
        self.ws_connections = {}
        self.request_id = 1
        self.stop_event = threading.Event()

    def fetch_usdt_pairs(self):
        response = requests.get(BINANCE_CONTRACT_API)
        data = response.json()
        return [s["symbol"] for s in data["symbols"] if s["quoteAsset"] == "USDT"]

    def update_symbol_list(self):
        """每小时更新USDT交易对列表"""
        while not self.stop_event.is_set():
            new_symbols = self.fetch_usdt_pairs()
            if set(new_symbols) != set(self.symbols):
                self.symbols = new_symbols
                self.stop_all()  # 断开当前WebSocket连接
                self.start_monitoring()  # 重新启动监控
            time.sleep(86400)  # 每小时更新一次

    def start_monitoring(self):
        if not hasattr(self, "update_thread"):
            self.update_thread = threading.Thread(target=self.update_symbol_list, daemon=True)
            self.update_thread.start()
        
        """启动所有 WebSocket 连接，每个连接最多订阅 200 个流。"""
        for i in range(0, len(self.symbols), STREAM_LIMIT):
            batch_symbols = self.symbols[i:i + STREAM_LIMIT]
            stream_names = [f"{symbol.lower()}@aggTrade" for symbol in batch_symbols]
            self.create_ws_connection(stream_names, batch_id=i // STREAM_LIMIT)

    def create_ws_connection(self, stream_names, batch_id):
        """为一批交易对创建 WebSocket 连接。"""
        ws_url = BINANCE_WS_BASE_URL + "/".join(stream_names)

        def on_open(ws):
            print(f"[INFO] WebSocket {batch_id} opened for {stream_names[:3]}...")

        def on_message(ws, message):
            data = json.loads(message)
            if data.get("stream").endswith("aggTrade"):
                self.process_trade(data["data"])

        def on_error(ws, error):
            print(f"[ERROR] WebSocket {batch_id} error: {error}. Reconnecting...")
            self.reconnect_ws(batch_id, stream_names)

        def on_close(ws, close_status_code, close_msg):
            print(f"[WARNING] WebSocket {batch_id} closed. Reconnecting...")
            self.reconnect_ws(batch_id, stream_names)

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        # 使用字典记录 WebSocket 连接
        self.ws_connections[batch_id] = ws

        # 启动 WebSocket 连接线程
        wst = threading.Thread(target=ws.run_forever, kwargs={"ping_interval": 60, "ping_timeout": 10})
        wst.start()

    def process_trade(self, trade):
        symbol = trade["s"]
        price = float(trade["p"])
        quantity = float(trade["q"])
        volume = price * quantity
        trade_time = datetime.utcfromtimestamp(trade["T"] / 1000)  # 使用 trade_time 变量

        # 检查是否进入新的一分钟
        trade_minute = trade_time.minute
        if trade_minute != self.current_minute:
            # 进入新的一分钟，仅重置每个代币的买卖成交量，而不重新初始化整个volume_data
            for symbol in self.volume_data:
                self.volume_data[symbol]["buy"] = 0
                self.volume_data[symbol]["sell"] = 0
            self.current_minute = trade_minute  # 更新当前分钟

        # 根据交易方向更新买卖成交量
        if trade["m"]:
            # Maker 订单 - 卖出
            self.volume_data[symbol]["sell"] += volume
        else:
            # Taker 订单 - 买入
            self.volume_data[symbol]["buy"] += volume

        # 调用价格波动检查
        self.check_1m_fluctuation(symbol, price, self.volume_data[symbol], trade_time)
        self.last_prices[symbol] = price
        print(f"[DEBUG] {symbol} - Latest Price: {price}, Quantity: {quantity}, Volume: {volume}, Time: {trade_time}")

    def reconnect_ws(self, batch_id, stream_names, delay=RECONNECT_DELAY):
        """指数退避重连机制"""
        print(f"[INFO] Attempting to reconnect WebSocket {batch_id} after {delay} seconds...")
        time.sleep(delay)
        self.create_ws_connection(stream_names, batch_id)
        RECONNECT_DELAY = min(RECONNECT_DELAY * 2, 300)  # 每次重连延长至最大5分钟

    def stop_all(self):
        """停止所有 WebSocket 连接，并等待所有线程结束。"""
        self.stop_event.set()  # 设置停止标志

        for ws in self.ws_connections.values():
            ws.close()

        # 确保所有线程都已终止
        for thread in threading.enumerate():
            if thread is not threading.main_thread():
                thread.join()

    def fetch_24hr_price_change(self, symbol):
        """调用 REST API 获取指定交易对的 24 小时价格变动数据。"""
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        try:
            response = requests.get(url, params={"symbol": symbol})
            data = response.json()
            return {
                "priceChangePercent": float(data["priceChangePercent"]),
                "lastPrice": float(data["lastPrice"]),
                "volume": float(data["quoteVolume"])
            }
        except requests.RequestException as e:
            print(f"[ERROR] Failed to fetch 24hr data for {symbol}: {e}")
            return None

    def check_1m_fluctuation(self, symbol, current_price, volume, trade_time):
        if symbol in self.last_prices:
            base_price = self.triggered_price_1m.get(symbol, self.last_prices[symbol])
            price_change = (current_price - base_price) / base_price

            # 获取买入和卖出累计成交量，取较大的一方
            buy_volume = self.volume_data[symbol]["buy"]
            sell_volume = self.volume_data[symbol]["sell"]
            dominant_volume = max(buy_volume, sell_volume)
            dominant_flow = "流入" if buy_volume > sell_volume else "流出"
            flow_dir = "🟢" if buy_volume > sell_volume else "🔴"    

            # 检查条件并打印 Debug 信息
            print(f"[DEBUG] Checking 1-Minute Fluctuation for {symbol}")
            print(f"  Base Price: {base_price}, Current Price: {current_price}")
            print(f"  Price Change: {price_change * 100:.2f}%, Dominant Volume: {dominant_volume} USDT")
            print(f"  Buyer (raw): {self.volume_data[symbol]['buy']} USDT, Seller (raw): {self.volume_data[symbol]['sell']} USDT")
            print(f"  Buyer: {buy_volume} USDT, Seller: {sell_volume} USDT, Dominant Volume: {dominant_volume} USDT")

            if abs(price_change) >= FLUCTUATION_THRESHOLD_1M and dominant_volume > VOLUME_THRESHOLD:
                print(f"[DEBUG] 1-Minute Trigger Conditions Met for {symbol}")
                time_since_last_trigger = (
                    trade_time - self.triggered_time_1m.get(symbol, trade_time)
                ).total_seconds()

                time = (
                      f"{int(time_since_last_trigger)} seconds" if time_since_last_trigger < 60 else "1 min"
                )

                data_24hr = self.fetch_24hr_price_change(symbol)
                if data_24hr is not None:
                    self.vol_24h[symbol] = data_24hr["volume"]

                self.send_telegram_alert(
                    symbol, current_price, price_change, dominant_volume, time, "1m",
                    dominant_flow, flow_dir, buy_volume, sell_volume
                )
                self.triggered_time_1m[symbol] = trade_time
                self.triggered_price_1m[symbol] = current_price
            else:
                print(f"[DEBUG] 1-Minute Trigger Conditions NOT Met for {symbol}")
                if (trade_time - self.triggered_time_1m.get(symbol, trade_time)).total_seconds() >= 60:
                    self.triggered_price_1m[symbol] = current_price

    def check_1h_fluctuation(self, symbol, current_price):
        # Check 1-hour fluctuation against baseline price
        
        if symbol in self.hourly_baseline and self.hourly_baseline[symbol] is not None:
            baseline_price = self.hourly_baseline[symbol]
            price_change = (current_price - baseline_price) / baseline_price

            # Only trigger alert once per hour for a symbol
        if abs(price_change) >= FLUCTUATION_THRESHOLD_1H and symbol not in self.alert_triggered_1h:
            # 计算当前时间与整点基准时间的分钟差
            minutes_since_baseline = int((datetime.utcnow() - datetime.combine(
                datetime.utcnow().date(), datetime.utcnow().time().replace(minute=0, second=0, microsecond=0)
            )).total_seconds() / 60)

            time = f"{minutes_since_baseline} min"

            # 设置已触发标志并发送提醒
            self.alert_triggered_1h.add(symbol)
            self.alert_count_1h[symbol] += 1  # 增加小时内预警数

            # 调用提醒函数
            self.send_telegram_alert(
                symbol,
                current_price,
                price_change,
                self.vol_24h.get(symbol, 0.0),
                f"{minutes_since_baseline} min",
                "1h"
            )
    def format_volume(self, volume):
        """格式化成交量为带单位的字符串（K, M, B等）"""
        if volume >= 1_000_000_000:
            return f"{volume / 1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            return f"{volume / 1_000_000:.2f}M"
        elif volume >= 1_000:
            return f"{volume / 1_000:.2f}K"
        else:
            return f"{volume:.2f}"

    def send_telegram_alert(self, symbol, price, price_change, volume, time, interval_type, dominant_flow, flow_dir, buy_volume, sell_volume):
        # 判断涨跌方向
        change_dir = "📈" if price_change > 0 else "📉"
    
        # 获取 24 小时涨跌幅
        data_24hr = self.fetch_24hr_price_change(symbol)
        if data_24hr is None:
            print(f"[ERROR] Could not fetch 24hr data for {symbol}. Skipping alert.")
            return
        percent_change_24h = data_24hr["priceChangePercent"]
        change_text_24h = f"{percent_change_24h:+.2f}%"

        # 计算占比
        flow_percentage = (dominant_volume / volume) * 100

        # 格式化成交量
        total_volume = self.format_volume(volume)
        dominant_volume_formatted = self.format_volume(dominant_volume)
        vol_24h = self.format_volume(self.vol_24h.get(symbol, 0.0))

        # 1小时预警星星数
        alert_count = self.alert_count_1h[symbol]
        alert_stars = "🌟" * alert_count + ("💥" if alert_count >= 4 else "")

        # 调整时间间隔格式
        interval_display = f"{time} change: {price_change * 100:+.2f}% {change_dir}"

        # 消息格式化
        message = (
            f"${symbol} | #{symbol}_USDT\n"
            f"Price: {price:.4f} ({change_text_24h} in 24h)\n"
            f"└ {interval_display}\n"
            f"{total_volume} USDT traded in {time}\n"
            f"└ {dominant_flow}: {dominant_volume_formatted} USDT [{flow_percentage:.1f}%] {flow_dir}\n"
            f"24h Vol: {vol_24h} USDT\n"
            f"1小时预警数: {alert_count} {alert_stars}"
        )
        self.send_telegram_message(message)

    def send_telegram_message(self, message):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        try:
            requests.post(url, data=data)
        except requests.RequestException as e:
            print(f"Failed to send Telegram message: {e}")

if __name__ == "__main__":
    monitor = BinanceMonitor()
    try:
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("Stopping monitor...")
        monitor.stop_all()
