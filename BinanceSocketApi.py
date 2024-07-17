import asyncio
import websockets
import json
import requests
import hmac
import hashlib
import time

API_KEY = 'JbExHGJHKVTPYmwmc6YTgghzAzvmtinQbE0q8lN1D4FYKQqfUQddMEnI5QFDo3OG'
API_SECRET = 'GKSG3ahQyW9MHWy12FdEyXOdLGZLQLX6C1UiN60OM9L8cVIWi9ssKCnaSSmibHkv'

def get_listen_key():
    url = 'https://fapi.binance.com/fapi/v1/listenKey'
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('listenKey')
    else:
        raise Exception(f"Failed to get listen key: {response.text}")

async def keep_alive_listen_key(listen_key):
    url = 'https://fapi.binance.com/fapi/v1/listenKey'
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    while True:
        response = requests.put(url, headers=headers, data={'listenKey': listen_key})
        if response.status_code != 200:
            print(f"Failed to keep listen key alive: {response.text}")
        await asyncio.sleep(1800)  # 每30分钟延长一次有效期

async def handle_websocket_message(message):
    data = json.loads(message)
    if 'e' in data:
        event_type = data['e']
        if event_type == 'ACCOUNT_UPDATE':
            print("账户更新信息：", json.dumps(data, indent=4))
        elif event_type == 'ORDER_TRADE_UPDATE':
            print("订单交易更新信息：", json.dumps(data, indent=4))
        else:
            print("其他事件：", json.dumps(data, indent=4))

async def get_account_info():
    listen_key = get_listen_key()

    # 启动心跳协程，保持 listen key 的有效性
    asyncio.create_task(keep_alive_listen_key(listen_key))

    url = f"wss://fstream.binance.com/ws/{listen_key}"
    async with websockets.connect(url) as websocket:
        while True:
            try:
                message = await websocket.recv()
                await handle_websocket_message(message)
            except websockets.exceptions.ConnectionClosed as e:
                print(f"连接关闭，尝试重新连接: {e}")
                break
            except Exception as e:
                print(f"接收消息时出错: {e}")
                break

# 主函数
async def main():
    await get_account_info()

# 运行主函数
asyncio.run(main())
