import time
from hax_we.binance_ws_manager import BinanceWebSocketManager
from hax_we.trigger_conditions import TriggerConditions
from hax_we.telegram_notifier import TelegramNotifier
from hax_we.api_client import get_24hr_ticker
from hax_we.utils import calculate_trade_volume


# 初始化 Binance WebSocket Manager
ws_manager = BinanceWebSocketManager()

# 初始化触发条件检测模块
trigger_conditions = TriggerConditions()

# 初始化 Telegram 通知模块
telegram_notifier = TelegramNotifier()

# 获取 24 小时涨跌数据
def fetch_24hr_data(symbol):
    data = get_24hr_ticker(symbol)
    return {
        "price_change": data["priceChange"],
        "price_change_percent": data["priceChangePercent"],
        "volume": data["quoteVolume"],
    }

# WebSocket 消息处理回调函数
def on_message(data):
    # 获取当前价格和成交量
    symbol = data["s"]
    current_price = float(data["p"])
    quantity = float(data["q"])
    trade_volume_usdt = calculate_trade_volume(current_price, quantity)

    # 更新触发条件模块中的价格和成交量数据
    trigger_conditions.update(symbol, current_price, trade_volume_usdt, data["m"])

    # 检查是否满足触发条件
    if trigger_conditions.check_trigger(symbol):
        # 获取 24 小时涨跌数据
        ticker_data = fetch_24hr_data(symbol)
        
        # 计算并格式化提醒消息
        message = telegram_notifier.format_message(
            symbol=symbol,
            current_price=current_price,
            price_change_percent=ticker_data["price_change_percent"],
            trade_volume=trigger_conditions.get_trade_volume(symbol),
            inflow_outflow=trigger_conditions.get_inflow_outflow(symbol),
            hour_alert_count=trigger_conditions.get_hour_alert_count(symbol),
            daily_volume=ticker_data["volume"]
        )

        # 发送提醒到 Telegram
        telegram_notifier.send_message(message)

# 启动 WebSocket 监听
ws_manager.start(on_message)

# 主循环，定期更新基准价格并检查一小时涨跌幅
try:
    while True:
        # 每小时更新一次基准价格
        current_hour = int(time.time() // 3600)
        if current_hour != trigger_conditions.last_hour:
            trigger_conditions.update_baseline_prices()
            trigger_conditions.last_hour = current_hour

        time.sleep(1)  # 控制主循环频率
except KeyboardInterrupt:
    print("程序已终止")
finally:
    ws_manager.stop()
