import json
import websocket
import threading

from config import memcache_client, crypto_names_price, logger

# Binance WebSocket的基础URL
SPOT_BASE_URL = "wss://stream.binance.com:9443/ws"
FUTURES_BASE_URL = "wss://fstream.binance.com/ws"


# 存储最新价格数据
last_price_data = {name: {"SwapAsk": None, "SpotAsk": None, "SwapBid": None, "SpotBid": None, "SwapAskSz": None, "SpotAskSz": None, "SwapBidSz": None, "SpotBidSz": None} for name in crypto_names_price}

# 初始化计数器
on_spot_message_count = 0
on_futures_message_count = 0

# 定义处理现货市场数据的回调函数
def on_spot_message(ws, message):
    data = json.loads(message)
    symbol = data['s']
    currency = symbol.replace("USDT", "")
    last_price_data[currency]["SpotBid"] = data['b']
    last_price_data[currency]["SpotAsk"] = data['a']
    last_price_data[currency]["SpotBidSz"] = data['B']
    last_price_data[currency]["SpotAskSz"] = data['A']

    # 将数据存入memcache缓存中
    memcache_client.set(f"{currency}SpotBid", last_price_data[currency]["SpotBid"])
    memcache_client.set(f"{currency}SpotAsk", last_price_data[currency]["SpotAsk"])
    memcache_client.set(f"{currency}SpotBidSz", last_price_data[currency]["SpotBidSz"])
    memcache_client.set(f"{currency}SpotAskSz", last_price_data[currency]["SpotAskSz"])

    global on_spot_message_count
    if on_spot_message_count <= 10:  # 程序启动，为了知道是否正确获取到了信息，仅仅显示前10条信息
        on_spot_message_count += 1
        logger.info(f"Spot Data - {currency}: Bid Price: {data['b']}, Ask Price: {data['a']}, Bid Size: {data['B']}, Ask Size: {data['A']}")

# 定义处理永续合约市场数据的回调函数
def on_futures_message(ws, message):
    data = json.loads(message)
    symbol = data['s']
    currency = symbol.replace("USDT", "")
    last_price_data[currency]["SwapBid"] = data['b']
    last_price_data[currency]["SwapAsk"] = data['a']
    last_price_data[currency]["SwapBidSz"] = data['B']
    last_price_data[currency]["SwapAskSz"] = data['A']

    # 将数据存入memcache缓存中
    memcache_client.set(f"{currency}SwapBid", last_price_data[currency]["SwapBid"])
    memcache_client.set(f"{currency}SwapAsk", last_price_data[currency]["SwapAsk"])
    memcache_client.set(f"{currency}SwapBidSz", last_price_data[currency]["SwapBidSz"])
    memcache_client.set(f"{currency}SwapAskSz", last_price_data[currency]["SwapAskSz"])

    global on_futures_message_count
    if on_futures_message_count <= 10:  # 程序启动，为了知道是否正确获取到了信息，仅仅显示前10条信息
        on_futures_message_count += 1
        logger.info(f"Futures Data - {currency}: Bid Price: {data['b']}, Ask Price: {data['a']}, Bid Size: {data['B']}, Ask Size: {data['A']}")

def on_open(ws):
    logger.info("WebSocket connected")

def on_error(ws, error):
    logger.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    logger.info(f"WebSocket closed with code: {close_status_code}, message: {close_msg}")

def start_websocket(url, on_message):
    ws = websocket.WebSocketApp(url, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws.run_forever()

if __name__ == "__main__":
    spot_threads = []
    for name in crypto_names_price:
        symbol = f"{name.lower()}usdt"
        spot_url = f"{SPOT_BASE_URL}/{symbol}@bookTicker"
        thread = threading.Thread(target=start_websocket, args=(spot_url, on_spot_message))
        thread.start()
        spot_threads.append(thread)

    futures_threads = []
    for name in crypto_names_price:
        symbol = f"{name.lower()}usdt"
        futures_url = f"{FUTURES_BASE_URL}/{symbol}@bookTicker"
        thread = threading.Thread(target=start_websocket, args=(futures_url, on_futures_message))
        thread.start()
        futures_threads.append(thread)

    for thread in spot_threads + futures_threads:
        thread.join()
