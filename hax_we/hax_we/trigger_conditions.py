# trigger_conditions.py
from datetime import datetime
from collections import defaultdict
from hax_we.telegram_notifier import TelegramNotifier
from hax_we.api_client import get_24hr_ticker
from config import PRICE_CHANGE_THRESHOLD, VOLUME_THRESHOLD_USDT
from hax_we.utils import calculate_trade_volume

class TriggerConditions:
    def __init__(self, telegram_notifier):
        self.price_data = defaultdict(lambda: {
            "price": None, "last_trigger_price": None, "hourly_base_price": None, "last_trigger_time": None,
            "hourly_warning_count": 0, "buy_volume": 0, "sell_volume": 0
        })
        self.telegram_notifier = telegram_notifier
        self.triggered_in_current_hour = set()
        
    def update_price(self, symbol, current_price, trade_volume_usdt, trade_time):
        now = datetime.utcnow()
        data = self.price_data[symbol]

        trade_volume_usdt = calculate_trade_volume(current_price, quantity)  # 调用 calculate_trade_volume

        # 累计买方和卖方成交量
        if is_buy:
            data["buy_volume"] += trade_volume_usdt
        else:
            data["sell_volume"] += trade_volume_usdt

        # 计算流入流出量
        if data["buy_volume"] > data["sell_volume"]:
            flow_in_out = data["buy_volume"] - data["sell_volume"]
            flow_percent = (data["buy_volume"] / (data["buy_volume"] + data["sell_volume"])) * 100
        else:
            flow_in_out = data["sell_volume"] - data["buy_volume"]
            flow_percent = (data["sell_volume"] / (data["buy_volume"] + data["sell_volume"])) * 100

        # 计算价格波动幅度
        if data["price"] is not None:
            price_change = (current_price - data["price"]) / data["price"]
            volume_condition = trade_volume_usdt > VOLUME_THRESHOLD_USDT

            # 检查 1 分钟内 ±0.5% 的波动 + 成交量条件
            if abs(price_change) >= PRICE_CHANGE_THRESHOLD and volume_condition:
                self.trigger_price_alert(symbol, current_price, trade_time, data)

        # 每小时基准价记录
        self.check_hourly_price(symbol, current_price, trade_time)
        
        # 更新当前价格
        data["price"] = current_price
    
    def trigger_price_alert(self, symbol, current_price, trade_time, data):
        now = datetime.utcnow()
        
        # 如果之前已经触发过，检查是否满足连续触发条件
        if data["last_trigger_time"]:
            time_since_last_trigger = (now - data["last_trigger_time"]).total_seconds()
            price_change_since_last_trigger = abs((current_price - data["last_trigger_price"]) / data["last_trigger_price"])
            
            if price_change_since_last_trigger >= PRICE_CHANGE_THRESHOLD:
                # 传递时间间隔为秒数，交给 Telegram 模块处理
                self.telegram_notifier.send_alert(symbol, current_price, "连续触发", time_since_last_trigger)
                data["last_trigger_price"] = current_price
                data["last_trigger_time"] = now
        else:
            # 初次触发
            self.telegram_notifier.send_alert(symbol, current_price, "初次触发", 0)
            data["last_trigger_price"] = current_price
            data["last_trigger_time"] = now
    
    def check_hourly_price(self, symbol, current_price, trade_time):
        now = datetime.utcnow()
        data = self.price_data[symbol]
        
        # 检查是否在整点，记录基准价
        if now.minute == 0 and now.second == 0:
            data["hourly_base_price"] = current_price
            self.triggered_in_current_hour.discard(symbol)
        
        # 检查是否满足 1 小时涨跌幅
        if data["hourly_base_price"] and not symbol in self.triggered_in_current_hour:
            hourly_change = (current_price - data["hourly_base_price"]) / data["hourly_base_price"]
            if abs(hourly_change) >= HOURLY_CHANGE_THRESHOLD:
                minutes_since_hour_start = int((now - now.replace(minute=0, second=0, microsecond=0)).total_seconds() // 60)
                self.telegram_notifier.send_alert(symbol, current_price, "小时涨跌幅触发", minutes_since_hour_start * 60)  # 以秒为单位传递
                self.triggered_in_current_hour.add(symbol)
    
    def debug_info(self):
        # 输出调试信息
        for symbol, data in self.price_data.items():
            print(f"{symbol}: 当前价格: {data['price']}, 上次触发价格: {data['last_trigger_price']}, 小时基准价格: {data['hourly_base_price']}")
