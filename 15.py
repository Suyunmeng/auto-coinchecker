import asyncio
import websockets

async def test_connection():
    url = "wss://fstream.binance.com/ws"  # 确保此处为正确的币安WebSocket URL
    try:
        async with websockets.connect(url) as ws:
            print("Connected to WebSocket successfully!")
            await ws.recv()  # 等待响应以验证连接有效
    except websockets.exceptions.InvalidStatusCode as e:
        print(f"Connection failed: {e}")

asyncio.run(test_connection())