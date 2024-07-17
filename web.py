import gzip
import io
import json

import requests
from flask import Flask, jsonify, request, Response
import threading
import time

from BinanceRestApi import do_init_account, BinanceRestAPI, do_close_account
from UserAccount import UserAccount
from config import memcache_client, logger
from db.get_funding_fee import get_funding_fee
from db.get_user_account import get_user_account_by_uid

"""
常见错误编码
成功代码
200: 成功 (OK)
客户端错误
400: 错误请求 (Bad Request) - 服务器无法理解请求。
401: 未授权 (Unauthorized) - 请求要求身份验证。
403: 禁止 (Forbidden) - 服务器拒绝请求。
404: 未找到 (Not Found) - 服务器找不到请求的资源。
405: 方法不允许 (Method Not Allowed) - 请求方法被禁止。
408: 请求超时 (Request Timeout) - 服务器等待请求超时。
409: 冲突 (Conflict) - 请求与服务器当前状态冲突。
服务器错误
500: 内部服务器错误 (Internal Server Error) - 服务器遇到未预料的情况。
501: 未实现 (Not Implemented) - 服务器不支持请求方法。
502: 错误网关 (Bad Gateway) - 网关或代理从上游服务器收到无效响应。
503: 服务不可用 (Service Unavailable) - 服务器当前无法处理请求。
504: 网关超时 (Gateway Timeout) - 网关或代理服务器等待上游服务器超时。
自定义错误码
201: 任务进行中 (Task is running. Just wait.)
203: 任务已完成 (Task completed. You can redo it after 5 minutes.)
500: 系统错误 (System error. Contact jack.)
501: 任务错误 (Task error. You can retry it after 5 minutes.)
502: 登录失败 (Unable to login)

"""
app = Flask(__name__)

# 定义中转服务的路由
@app.route('/proxy', methods=['GET', 'POST'])
def proxy():
    proxy_url = request.args.get('proxy_url')
    if not proxy_url:
        return jsonify({"error": "URL is required"}), 400

    # 复制params并移除url参数
    proxy_params = request.args.copy()
    proxy_params.pop('proxy_url', None)

    # 获取并复制 headers
    proxy_headers = dict(request.headers)
    # 删除不需要的 headers
    if proxy_url == "https://api.binance.com/api/v3/time":  # 获取时间的函数，不能有这些头部信息
        proxy_headers.pop('Host', None)
        proxy_headers.pop('User-Agent', None)
        proxy_headers.pop('Accept-Encoding', None)
        proxy_headers.pop('Accept', None)
        proxy_headers.pop('Connection', None)

    if request.method == 'GET':
        response = requests.get(proxy_url, params=proxy_params, headers=proxy_headers)
    elif request.method == 'POST':
        response = requests.post(proxy_url, params=proxy_params, headers=proxy_headers)

    logger.info(f"proxy {response.status_code} : {response.content}")
    return (response.content, response.status_code, response.headers.items())


doInitAccount_locks = {}  # 创建一个全局字典来跟踪每个用户的锁


@app.route('/doInitAccount', methods=['GET'])
def http_doInitAccount():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login, please check your key"})
    logger.info(f"Congratulations! http_doInitAccount Login successfully, uid = {binance_rest_api.user_account.uid}")
    uid = binance_rest_api.user_account.uid

    # 创建或获取用户锁
    if uid not in doInitAccount_locks:
        doInitAccount_locks[uid] = threading.Lock()
    user_lock = doInitAccount_locks[uid]
    if user_lock.locked():
        return jsonify({"code": 201, "message": "Task is running. Just wait."})
    user_lock.acquire()

    def job_wrapper():  # 封装一个函数，主要目的是为了最终无论如何都释放用户锁
        try:
            do_init_account(binance_rest_api)
        finally:
            user_lock.release()

    # 通过数据库的记录，决定是否能执行建仓操作，不能的话，直接返回
    db_user_account = get_user_account_by_uid(uid)
    if db_user_account is None:  # 还没有创建过账户，可以继续进行
        pass
    elif db_user_account.account_state == 0:  # 策略已经关闭了，可以再次开启
        pass
    elif db_user_account.account_state == 1:  # 已经执行过策略了，不允许再次建仓
        user_lock.release()
        return jsonify({"code": 203, "message": "Task completed."})
    else:
        return jsonify({"code": 500, "message": "System error. Contact jack."})

    # 启动一个新线程来执行长时间任务
    threading.Thread(target=job_wrapper).start()
    return jsonify({"code": 200, "message": "Task submitted. You can wait for results."})


doCloseAccount_locks = {}  # 创建一个全局字典来跟踪每个用户的锁

@app.route('/doCloseAccount', methods=['GET'])
def http_doCloseAccount():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login, please check your key"})
    logger.info(f"Congratulations! http_doInitAccount Login successfully, uid = {binance_rest_api.user_account.uid}")
    uid = binance_rest_api.user_account.uid

    # 创建或获取用户锁
    if uid not in doCloseAccount_locks:
        doCloseAccount_locks[uid] = threading.Lock()
    user_lock = doCloseAccount_locks[uid]
    if user_lock.locked():
        return jsonify({"code": 201, "message": "Task is running. Just wait."})
    user_lock.acquire()

    def job_wrapper2():  # 封装一个函数，主要目的是为了最终无论如何都释放用户锁
        try:
            do_close_account(binance_rest_api)
            # print(f"Job started for user: {api_key}")
            # import time
            # time.sleep(10)  # 模拟长时间任务
            # print(f"Job completed for user: {api_key}")
        finally:
            user_lock.release()

    # 通过数据库的记录，决定是否能执行平仓操作，不能的话，直接返回
    db_user_account = get_user_account_by_uid(uid)
    if db_user_account is None:  # 还没有创建过账户
        user_lock.release()
        return jsonify({"code": 512, "message": "Attempted to close position before opening was completed."})
    elif db_user_account.account_state == 0:  # 策略已经是关闭状态了
        user_lock.release()
        return jsonify({"code": 203, "message": "Task completed."})
    elif db_user_account.account_state == 1:  # 可以执行关闭策略
        pass
    else:
        return jsonify({"code": 500, "message": "System error. Contact jack."})

    # 启动一个新线程来执行长时间任务
    threading.Thread(target=job_wrapper2).start()
    return jsonify({"code": 200, "message": "Task submitted. You can wait for results."})


@app.route('/make_balance', methods=['GET'])
def http_make_balance():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    symbol = request.args.get('symbol')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    binance_rest_api.make_balance(symbol)
    return Response({"code": 200}, mimetype='application/json')


@app.route('/do_order', methods=['GET'])
def http_do_order():
    """
    下订单
    /do_order?order_type=spot&symbol=RNDR&sz=68.2&side=sell&
    :return:
    """
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    order_type = request.args.get('order_type')
    symbol = request.args.get('symbol')
    sz = request.args.get('sz')
    side = request.args.get('side')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    ret = None
    if order_type == "spot":
        ret = binance_rest_api.doOrderSpot(symbol, float(sz), side)
    elif order_type == "swap":
        ret = binance_rest_api.doOrderSwap(symbol, float(sz), side)

    return jsonify({"code": ret, "message": ""})


@app.route('/do_hedge_trade_close', methods=['GET'])
def http_do_hedge_trade_close():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    order_type = request.args.get('order_type')
    symbol = request.args.get('symbol')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    ret = binance_rest_api.do_hedge_trade_close(symbol)
    return jsonify({"code": ret, "message": ""})


@app.route('/distribute', methods=['GET'])
def http_get_distribute():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    binance_rest_api.update_account()
    return Response(json.dumps(binance_rest_api.user_account.compute_crypto_percent()).encode('utf-8'), mimetype='application/json')


@app.route('/account', methods=['GET'])
def http_get_account():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    binance_rest_api.update_account()
    return Response(json.dumps(binance_rest_api.user_account.get_account_summary()).encode('utf-8'), mimetype='application/json')


@app.route('/funding_fee', methods=['GET'])
def http_get_funding_fee():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    startTime = request.args.get('startTime')
    endTime = request.args.get('endTime')
    if startTime is None or startTime == '':
        startTime = 0
    if endTime is None or endTime == '':
        endTime = 0

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    jsonStr = get_funding_fee(binance_rest_api, startTime=startTime, endTime=endTime)
    return Response(jsonStr, mimetype='application/json')


@app.route('/margin_interest', methods=['GET'])
def http_get_margin_interest():
    """    获取杠杆利息历史记录    """
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    startTime = request.args.get('startTime')
    endTime = request.args.get('endTime')
    if startTime is None or startTime == '':
        startTime = 0
    if endTime is None or endTime == '':
        endTime = 0

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    jsonStr = binance_rest_api.get_margin_interest_history()
    return Response(json.dumps(jsonStr).encode('utf-8'), mimetype='application/json')


@app.route('/do_margin_borrow_repay', methods=['GET'])
def http_do_margin_borrow_repay():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')
    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    symbol = request.args.get('symbol')
    amount = request.args.get('amount')
    type = request.args.get('type')
    jsonStr = binance_rest_api.do_margin_borrow_repay(symbol, float(amount), type)
    return Response(json.dumps(jsonStr).encode('utf-8'), mimetype='application/json')


@app.route('/account_status', methods=['GET'])
def http_get_account_status():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    jsonStr = binance_rest_api.get_account_status()
    return Response(json.dumps(jsonStr).encode('utf-8'), mimetype='application/json')


@app.route('/account_info', methods=['GET'])
def http_get_account_info():
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    jsonStr = binance_rest_api.get_account_info()
    return Response(json.dumps(jsonStr).encode('utf-8'), mimetype='application/json')


@app.route('/account_type', methods=['GET'])
def http_get_account_type():
    """
    通过这个 api 查询所有的用户门槛限制
    :return:
    """
    api_key = request.args.get('api_key')
    api_secret = request.args.get('api_secret')

    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        return jsonify({"code": 502, "message": "Unable to login"})
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    # 1、查询统一账户权限
    account_info = json.dumps(binance_rest_api.get_account_info())
    # : b'{"code":-2015,"msg":"Invalid API-key, IP, or permissions for action, request ip: 101.32.221.157"}'
    if "-2015" in account_info:
        return jsonify(account_info)

    jsonStr = json.dumps(binance_rest_api.get_sub_account_transfer())
    #  主账户会返回这个
    #  {"code": -12022, "msg": "This endpoint is allowed to request from sub account only"}
    #  子账户会返回
    # [
    #     {
    #         "counterParty": "subAccount",
    #         "email": "thompson_virtual@so5j9fk4noemail.com",      #  包含  _virtual  就是虚拟子账户
    #         "type": 2,
    #         "asset": "USDT",
    #         "qty": "10000.00000000",
    #         "time": 1719808298000,
    #         "status": "SUCCESS",
    #         "tranId": 180476945977,
    #         "fromAccountType": "SPOT",
    #         "toAccountType": "USDT_FUTURE"
    #     }
    # ]
    # 子账户没钱会返回
    # []
    # return Response(json.dumps(jsonStr).encode('utf-8'), mimetype='application/json')

    logger.info(jsonStr)
    if "_virtual@" in jsonStr:
        return jsonify({"account_type": "virtual"})
    elif "from sub account only" in jsonStr:
        return jsonify({"account_type": "main"})
    else:  #  如果是 TODO []  则返回子账户没钱
        return jsonify(jsonStr)


if __name__ == '__main__':
    app.run(debug=True)

