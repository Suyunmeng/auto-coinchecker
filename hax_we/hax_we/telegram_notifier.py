# telegram_notifier.py
import requests

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_alert(self, symbol, current_price, price_change, volume_usdt, flow_in_out, flow_percent, hourly_volume_usdt, hourly_warning_count, time_in_seconds, last_trigger_price=None):
        """构建并发送价格波动和成交量的提醒消息"""
        time_message = self._format_time_message(time_in_seconds)
        price_change_message = f"{price_change:.2f}% {'📈' if price_change >= 0 else '📉'}"
        if flow_in_out >= 0:
            flow_message = f"流入: {flow_in_out:.2f} USDT [{flow_percent:.0f}%] 🟢"
        else:
            flow_message = f"流出: {abs(flow_in_out):.2f} USDT [{abs(flow_percent):.0f}%] 🔴"
        
        volume_message = self._format_large_number(volume_usdt)
        hourly_volume_message = self._format_large_number(hourly_volume_usdt)
        
        ticker_data = get_24hr_ticker(f"{symbol}USDT")
        if ticker_data:
            twenty_four_hour_change = float(ticker_data['priceChangePercent'])  # 获取24小时的百分比涨跌幅
        else:
            twenty_four_hour_change = 0.0  # 如果获取数据失败，默认为0
     
        message = f"""
        ${symbol} | #{symbol}_USDT
        Price: {current_price} ({twenty_four_hour_change:+.2f}% in 24h)
        └ {time_message} change: {price_change_message}
        {volume_message} USDT traded in {time_message}
        └ {flow_message}
        24h Vol: {hourly_volume_message} USDT
        1小时预警数: {self._format_warning_count(hourly_warning_count)}
        """
        self._send_message(message)

    def _format_time_message(self, time_in_seconds):
        """将时间秒数转换为消息显示格式"""
        if time_in_seconds < 60:
            return f"{int(time_in_seconds)} 秒"
        else:
            minutes = int(time_in_seconds // 60)
            if minutes == 1:
                return "1 min"
            return f"{minutes} min"
    
    def _format_large_number(self, number):
        """格式化成交量数值，单位化显示（K, M, B）"""
        if number >= 1_000_000:
            return f"{number / 1_000_000:.2f}M"
        elif number >= 1_000:
            return f"{number / 1_000:.2f}K"
        return f"{number:.2f}"

    def _format_warning_count(self, count):
        """格式化 1 小时内的预警数"""
        return "💥" if count >= 4 else "🌟" * count

    def _send_message(self, message):
        """发送消息到 Telegram"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {"chat_id": self.chat_id, "text": message}
        requests.post(url, data=data)
