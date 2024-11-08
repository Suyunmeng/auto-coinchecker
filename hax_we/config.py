# config.py
# config.py
BINANCE_API_BASE_URL = "https://fapi.binance.com"  # Binance API 基础路径
BASE_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
WS_BASE_URL = "wss://fstream.binance.com"
PING_INTERVAL = 180  # 秒
PING_TIMEOUT = 600  # 秒
RECONNECT_DELAY = 5  # 秒
# config.py
PRICE_CHANGE_THRESHOLD = 0.005       # 1分钟内价格波动 ±0.5%
VOLUME_THRESHOLD_USDT = 30000        # 成交量条件 > 30000 USDT
HOURLY_CHANGE_THRESHOLD = 0.02       # 每小时涨跌幅 ±2%
PING_INTERVAL = 180                  # WebSocket ping间隔时间（秒）
PING_TIMEOUT = 600                   # WebSocket ping超时时间（秒）
RECONNECT_DELAY = 5                  # WebSocket 重连延迟时间（秒）

