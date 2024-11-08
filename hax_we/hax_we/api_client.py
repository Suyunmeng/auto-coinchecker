# api_client.py
import requests
from config import BINANCE_API_BASE_URL

def get_24hr_ticker(symbol):
    """获取指定交易对的24小时价格变动数据"""
    url = f"{BINANCE_API_BASE_URL}/fapi/v1/ticker/24hr"
    params = {'symbol': symbol}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # 检查请求是否成功
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching 24hr ticker data for {symbol}: {e}")
        return None
