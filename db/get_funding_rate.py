import time

import requests
from datetime import datetime, timedelta

from binance import Client

from config import db_config
from db.connect_to_db import connect_to_db


# 从数据库获取最新资金费率时间的函数
def get_latest_funding_time(cursor, instrument_id):
    query = "SELECT fundingTime FROM funding_rate WHERE symbol = %s ORDER BY fundingTime DESC LIMIT 1"
    cursor.execute(query, (instrument_id,))
    result = cursor.fetchone()
    return result[0] if result else None


# 将资金费率保存到数据库的函数
def save_rates_to_db(cursor, rates):
    insert_query = """
    INSERT IGNORE INTO funding_rate (fundingTime, symbol, fundingRate, markPrice)
    VALUES (%s, %s, %s, %s, %s)
    """
    for rate in rates:
        cursor.execute(insert_query,
                       int(rate['fundingTime'],
                           rate['symbol'],
                           rate['fundingRate'],
                           rate['markPrice']
                           ))


# 获取产品历史资金费率的主要函数
def get_historical_funding_rate(symbol, days=700):
    cnx = connect_to_db(db_config)
    if not cnx:
        return []
    cursor = cnx.cursor()
    start_time = int(time.time() - 86400 * days) * 1000
    db_latest_time = get_latest_funding_time(cursor, symbol)  # 查询数据库中最新的数据的 时间
    if db_latest_time is not None:
        # 获取资金费率
        limit = (time.time() * 1000 - db_latest_time) / 86400000 * 10  # 假设每天最多24次资金费（4小时1次，是6次)
        rates = get_funding_rate_history_api(symbol, db_latest_time, limit=limit)
        # 确保records是按照时间戳 fundingTime 排序的
        rates.sort(key=lambda x: int(x['fundingTime']))
        # 保存到数据库
        save_rates_to_db(cursor, rates)
        cnx.commit()
    else:   # 初始化数据
        # 获取资金费率
        rates = get_funding_rate_history_api(symbol, start_time)
        # 确保records是按照时间戳 fundingTime 排序的
        rates.sort(key=lambda x: int(x['fundingTime']))
        # 保存到数据库
        save_rates_to_db(cursor, rates)
        cnx.commit()

    # 获取数据库中的资金费率记录
    query = ("SELECT * FROM funding_rate WHERE symbol = %s AND fundingTime >= %s")
    cursor.execute(query, (symbol, start_time))
    all_rates = cursor.fetchall()

    cursor.close()
    cnx.close()
    return all_rates

# 初始化Binance客户端
client = Client()

def get_funding_rate_history_api(symbol, start_time, limit = 100):
    all_rates = []
    stop_time = int(time.time() * 1000)  #
    real_start_time = start_time  # 设定的天数前的时间戳

    while True:
        params = {
            'symbol': symbol,
            'limit': limit,
            'start_time': start_time
        }
        response = client.futures_funding_rate(**params)
        if response:
            all_rates.extend(response)
            start_time = response[-1]['fundingTime'] - 1  # 更新end_time为最后一条数据的时间戳, 继续查询时间更靠后的数据
            if len(response) < limit or start_time > stop_time:  # 如果返回数据少于请求数据，说明已经到最后一页
                break
        else:
            break

    # 过滤掉超出设定天数的数据
    all_rates = [rate for rate in all_rates if rate['fundingTime'] >= real_start_time]
    return all_rates

# # 示例用法
historical_rates = get_historical_funding_rate("BTCUSDT")
print(len(historical_rates))
