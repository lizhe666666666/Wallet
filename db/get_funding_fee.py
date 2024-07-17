import hashlib
import hmac
import json
import logging
import time
from decimal import Decimal

import requests
from datetime import datetime, timedelta, timezone

from BinanceRestApi import BinanceRestAPI
from UserAccount import UserAccount
from config import db_config
from db.connect_to_db import connect_to_db


# 从数据库获取最新的记录时间的函数
def get_latest_record_time(uid, cursor):
    query = "SELECT ts FROM funding_fee WHERE uid = %s ORDER BY ts DESC LIMIT 1"
    cursor.execute(query, (uid,))
    result = cursor.fetchone()
    if result:
        return result[0]
    return None


# 将记录保存到数据库的函数
def save_interest_to_db(cnx, cursor, _uid, records):
    insert_query = """
    INSERT IGNORE INTO funding_fee (uid, ts, symbol, income)
    VALUES (%s, %s, %s, %s)
    """
    # 确保records是按照时间戳time排序的
    records.sort(key=lambda x: int(x['time']))
    for record in records:
        cursor.execute(insert_query, (
            _uid,
            int(record['time']),
            record['symbol'],
            record['income']
        ))
    cnx.commit()


#  TODO 定时任务，每天都跑一遍，将最新数据刷新到数据库中
def get_funding_fee(rest_api: BinanceRestAPI, startTime=0, endTime=0):
    """
    返回资金费记录

    从数据库读取优先，数据库没有的，会通过api 读取
    api接口的数据会同步更新到数据库
    :param endTime:
    :param startTime:
    :type rest_api: BinanceRestAPI
    :return:
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logging.error("get_funding_fee  -- Failed to connect to the database. ")
        return json.dumps([])

    cursor = cnx.cursor()

    # 检查最新的记录
    incomes = rest_api.get_income(limit=1)
    logging.info(len(incomes))
    if(len(incomes)) == 0:  # 用户没数据，直接返回
        return json.dumps([])

    latest_time = get_latest_record_time(rest_api.user_account.uid, cursor)
    if latest_time is None:
        # 数据库没有记录，查询所有记录，并保存到数据库（初始化数据库的操作） TODO 整体数据同步需要考虑， 比如 7天没有更新数据的情况
        records = rest_api.get_income(startTime=rest_api.get_server_time()-7*86400000, endTime=rest_api.get_server_time(), limit=1000)  # 查询7天前的数据
        print("Records to save (initial):", records)
        save_interest_to_db(cnx, cursor, rest_api.user_account.uid, records)
    elif incomes[0]['time'] > latest_time:  # 数据库缺少最新数据  主动更新
        records = rest_api.get_income(startTime=latest_time, endTime=rest_api.get_server_time(), limit=1000)  #
        print("Records to save (update):", records)
        save_interest_to_db(cnx, cursor, rest_api.user_account.uid, records)

    # 获取数据库中的记录
    if endTime == 0:
        endTime = int(time.time() * 1000)
    query = "SELECT * FROM funding_fee WHERE uid = %s and ts >= %s and ts <= %s"
    cursor.execute(query, (rest_api.user_account.uid, startTime, endTime,))
    all_rates = cursor.fetchall()
    cursor.close()
    cnx.close()

    # 将数据库记录转换为 JSON 格式
    results = []
    for rate in all_rates:
        result = {
            "uid": rate[1],
            "ts": rate[2],
            "symbol": rate[3],
            "income": float(rate[4]) if isinstance(rate[4], Decimal) else rate[4]  # 转换 Decimal 为 float
        }
        print(result)
        results.append(result)

    return json.dumps(results)

if __name__ == "__main__":
    # # 李哲的账户  正式
    api_key = 'I8Z8dTV6aPQ80LEy7P7s3VSidAppKSA2EmhUTCj20XAfaLjRrGcfFsOanzXbddrK'
    api_secret = '3RR9d2tMSj23PKHMKf583BUI9Jigq4V0GbRXwWU9iwsJgse9DX0LSWptd9oLgxP5'

    # # 初始化用户账户, 包含完成初始建仓操作
    # do_init_account(api_key, api_secret)


    # 创建用户账户实例
    user_account = UserAccount(0, api_key, api_secret)
    # 为用户创建 BinanceRestAPI 实例
    simulated = 0
    binance_rest_api = BinanceRestAPI(simulated=simulated)
    uid = binance_rest_api.get_account_uid()
    if uid < 0:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        logging.info(f"User API Key Error {-uid}")
    logging.info(f"Congratulations! Login successfully, uid = {uid}")

    #  查询资金流水
    # get_funding_fee(binance_rest_api, startTime=1720051203000, endTime=1720051203000)
    get_funding_fee(binance_rest_api)


    logging.info(1)
