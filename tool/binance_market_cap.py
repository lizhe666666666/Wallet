import requests
from binance.client import Client
from pymemcache.client import base
import pandas as pd
from datetime import datetime, timedelta


# Binance API key and secret
api_key = 'JbExHGJHKVTPYmwmc6YTgghzAzvmtinQbE0q8lN1D4FYKQqfUQddMEnI5QFDo3OG'
api_secret = 'GKSG3ahQyW9MHWy12FdEyXOdLGZLQLX6C1UiN60OM9L8cVIWi9ssKCnaSSmibHkv'

# CoinMarketCap API key
cmc_api_key = 'f967c0cc-05cd-4b38-8af3-0761c911207b'

# 初始化Binance客户端
client = Client(api_key, api_secret)

# 初始化Memcached客户端
memcache_client = base.Client(('127.0.0.1', 11211))

def get_binance_symbols():
    exchange_info = client.get_exchange_info()
    symbols = {symbol['symbol'][:-4] for symbol in exchange_info['symbols'] if symbol['quoteAsset'] == 'USDT'}
    return symbols

def get_swap_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = {symbol['symbol'][:-4] for symbol in exchange_info['symbols'] if symbol['contractType'] == 'PERPETUAL'}
    return symbols

def get_market_caps(symbols):
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    headers = {
        'X-CMC_PRO_API_KEY': cmc_api_key,
    }
    params = {
        'symbol': ','.join(symbols),
        'convert': 'USD'
    }
    response = requests.get(url, headers=headers, params=params)
    data = response.json()

    market_caps = {}
    for symbol in symbols:
        if symbol.upper() in data['data']:
            market_caps[symbol] = data['data'][symbol.upper()]['quote']['USD']['market_cap']

    return market_caps

# 获取资金费率历史数据的函数
def get_funding_rate_history(symbol, days):
    all_rates = []
    limit = 1000  # 每次请求的最大数据量
    end_time = int(datetime.now().timestamp() * 1000)  # 当前时间戳，毫秒级
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)  # 设定的天数前的时间戳

    while True:
        params = {
            'symbol': symbol,
            'limit': limit,
            'endTime': end_time
        }
        response = client.futures_funding_rate(**params)
        if response:
            all_rates.extend(response)
            end_time = response[-1]['fundingTime'] - 1  # 更新end_time为最后一条数据的时间戳，往前查询
            if len(response) < limit or response[-1]['fundingTime'] < start_time:  # 如果返回数据少于请求数据，说明已经到最后一页
                break
        else:
            break

    # 过滤掉超出设定天数的数据
    all_rates = [rate for rate in all_rates if rate['fundingTime'] >= start_time]
    return all_rates

# 获取币安的现货和合约符号列表
spot_symbols = get_binance_symbols()
swap_symbols = get_swap_symbols()

# 取交集
common_symbols = spot_symbols.intersection(swap_symbols)

# 获取市值
market_caps = get_market_caps(common_symbols)

# 过滤市值超过10亿美元的币种，并保存到Memcached
swap_instruments = []
for symbol, market_cap in market_caps.items():
    if market_cap and market_cap > 1_000_000_000:
        print(f"Market Cap for {symbol}: ${market_cap:.2f}")
        memcache_client.set(f'CAPS_{symbol}', market_cap)
        swap_instruments.append(f"{symbol}USDT")


# 收集每个交易对的资金费率数据
funding_data = {}  # 资金费
variance_data = {}  # 资金费方差
data_count = {}  # 记录历史数据总数

three_months_ago = datetime.utcnow() - timedelta(days=90)

count = 0
for symbol in swap_instruments:
    count = count + 1
    print(count)

    data = get_funding_rate_history(symbol, 365)
    data_count[symbol] = len(data)  # 记录历史数据总数
    print(len(data))
    if data:
        df = pd.DataFrame(data)
        df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
        df['fundingRate'] = df['fundingRate'].astype(float)

        # 检查数据是否超过3个月
        earliest_date = df['fundingTime'].min()
        if earliest_date > three_months_ago:
            print(f"Discarding {symbol} due to insufficient data (less than 3 months).")
            continue

        funding_data[symbol] = df['fundingRate'].mean()
        print(funding_data[symbol])
        variance_data[symbol] = df['fundingRate'].var()

# 排序找到平均资金费率最大的前n名
top_20 = sorted(funding_data.items(), key=lambda item: item[1], reverse=True)[:200]

# 打印结果、方差和历史数据总数
print(f"代码\t平均年化资金费率\t方差\t数据条数\t市值")
for symbol, avg_rate in top_20:
    var = variance_data[symbol]
    count = data_count[symbol]
    # if (var * 1000000 < 0.20):  # 关于方差的筛选
    print(f"{symbol}\t{avg_rate * 100 * 3 * 365:.2f}%\t{var * 1000000:.4f}\t{count}\t{market_caps[symbol]}")
