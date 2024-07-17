import pprint
from decimal import Decimal

import requests
import time
import hmac
import hashlib

from RestAPI import RestAPI
from UserAccount import UserAccount
from config import memcache_client, logger, ENVIRONMENT, proxy_url, ORDER_USDT_MIN, crypto_names, crypto_percent
from db.get_user_account import update_user_account, update_account_state, get_user_account_by_uid, \
    get_user_account_by_api_key


class BinanceRestAPI(RestAPI):
    """Binance REST API具体实现类。"""
    def __init__(self, api_key, api_secret):
        """
        :param api_key:
        :param api_secret:
        :param proxy_url:  代理的URL
        """
        self.api_key = api_key
        self.api_secret = api_secret

        self.base_url = 'https://api.binance.com'
        self.futures_base_url = 'https://fapi.binance.com'
        self.universe_base_url = 'https://papi.binance.com'
        # 创建用户账户实例
        # 先从数据库获取 用户uid 如果没有，再通过 api 获取
        db_user_account = get_user_account_by_api_key(self.api_key, self.api_secret)
        if db_user_account is None:  # 还没有创建过账户, 通过API接口查询
            uid = self.get_account_uid()
            if uid < 0:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
                logger.info(f"User API Key Error {-uid}")
                return
            self.user_account = UserAccount(uid, api_key, api_secret)
            update_user_account(self.user_account)  # 创建用户数据库记录
        else:  # 使用数据库缓存数据
            self.user_account = UserAccount(db_user_account.uid, self.api_key, self.api_secret)

    def update_account(self):
        """
        获取账户配置信息，并更新信息到用户账户。
        :return: 响应数据
        """
        account_info_json = self.get_account_info()

        self.user_account.asset_valuation = float(account_info_json['actualEquity'])
        self.user_account.update_margin_rate(account_info_json['uniMMR'])
        self.user_account.accountStatus = account_info_json['accountStatus']

        # 更新所有账户信息
        self.update_all_balance()

        logger.info(f"Update account successfully")
        return {}

    ##########################################################################################
    # 非继承接口的函数
    def sign_request(self, params):
        """
        对请求进行签名。
        :param params: 请求参数
        :param secret: 私钥
        :return: 签名字符串
        """
        query_string = '&'.join([f"{d}={params[d]}" for d in params])
        return hmac.new(self.api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    def send_request(self, method, endpoint, params=None):
        """
        实现代理请求，通过配置文件来获取是否经过代理
        :param method:
        :param endpoint:
        :param params:
        :return:
        """
        #  TODO 是否需要 api_key  和  signature   做穿透，问题多多，暂时先搁置了。。。。。
        headers = None
        if endpoint != f"{self.base_url}/api/v3/time":  # 权重(IP): 1  仅仅获取时间的 API 不需要增加时间戳参数
            headers = {'X-MBX-APIKEY': self.api_key}
            if params is None:
                params = {}
            params['timestamp'] = self.get_server_time()
        if params is not None:
            params['signature'] = self.sign_request(params)
        if ENVIRONMENT == "development":  # TODO 本地开发环境，需要通过代理来返回请求数据
            # temp_url = f"{proxy_url}?proxy_url={endpoint}"
            # response = requests.request(method, temp_url, headers=headers, params=params)
            response = requests.request(method, endpoint, headers=headers, params=params)
        else:
            response = requests.request(method, endpoint, headers=headers, params=params)

        logger.info(f"send_request {endpoint} {response.status_code} : {response.content}")
        return response

    def get_server_time(self):
        """
        获取服务器时间。
        :return: 服务器时间戳
        """
        time_diff = memcache_client.get('server_time_diff')
        # time_diff = None
        if time_diff is None:
            url = f"{self.base_url}/api/v3/time"
            # response = requests.get(url)
            response = self.send_request("GET", url)
            server_time = response.json()['serverTime']
            local_time = int(time.time() * 1000)
            time_diff = server_time - local_time
            # logger.info(f"time_diff A={time_diff}")
            memcache_client.set('server_time_diff', time_diff, expire=1500)  # 缓存1500秒
        else:
            time_diff = int(time_diff)  # 将从 memcache 获取的值转换为整数
            # logger.info(f"time_diff B={time_diff}")
            local_time = int(time.time() * 1000)
            server_time = local_time + time_diff

        return server_time

    def get_account_info(self):
        """
        查询账户信息 (USER_DATA)
        {
            "uniMMR": "5167.92171923",   // 统一账户维持保证金率
            "accountEquity": "122607.35137903",   // 以USD计价的账户权益
            "actualEquity": "73.47428058",   // 不考虑质押率后的以USD计价账户权益
            "accountInitialMargin": "23.72469206",
            "accountMaintMargin": "23.72469206", // 以USD计价统一账户维持保证金
            "accountStatus": "NORMAL"   // 统一账户账户状态："NORMAL", "MARGIN_CALL", "SUPPLY_MARGIN", "REDUCE_ONLY", "ACTIVE_LIQUIDATION", "FORCE_LIQUIDATION", "BANKRUPTED"
            "virtualMaxWithdrawAmount": "1627523.32459208"  // 以USD计价的最大可转出
            "totalAvailableBalance":"",
            "totalMarginOpenLoss":"",
            "updateTime": 1657707212154 // 更新时间
        }
        :return:
        """
        url = f"{self.universe_base_url}/papi/v1/account"  # 权重(IP): 20
        response = self.send_request("GET", url)
        return response.json()

    def set_um_position_side(self, dualSidePosition: bool):
        params = {'dualSidePosition': dualSidePosition}
        url = f"{self.universe_base_url}/papi/v1/um/positionSide/dual"  # 权重(IP): 1
        response = self.send_request("POST", url, params=params)
        return response.json()

    def get_um_position_side(self):
        url = f"{self.universe_base_url}/papi/v1/um/positionSide/dual"  # 权重(IP): 1
        response = self.send_request("GET", url)
        return response.json()["dualSidePosition"]

    def set_bnbBurn(self):
        """ 设置 币安币 抵扣 """
        url = f"{self.base_url}/sapi/v1/bnbBurn"  # 权重(IP): 1
        params = {
            'spotBNBBurn': 'true',
            'interestBNBBurn': 'true'
        }
        response = self.send_request("POST", url, params=params)
        return response.json()

    def get_dust_assets(self):
        """
        获取可转换 的 灰尘资产资产
        :return:
        """
        url = f"{self.base_url}/sapi/v1/asset/dust-btc"  # 权重(IP): 1
        response = self.send_request("POST", url)
        return response.json()

    def convert_dust_to_bnb(self, assets):
        """
        执行灰尘转换
        :return:
        """
        url = f"{self.base_url}/sapi/v1/asset/dust"  # 权重(UID): 10
        params = {'asset': assets}
        response = self.send_request("POST", url, params=params)
        return response.json()

    def do_dust_to_bnb(self):
        """
        执行完整的小额货币转换为BNB  TODO 竟然没有获取到 asset 信息？？ 难道只能操作现货里面的东西？ 需要先转移一下？
        :return:
        """
        dust_assets_json = self.get_dust_assets()
        assets_to_convert = [detail['asset'] for detail in dust_assets_json['details']]
        if len(assets_to_convert) > 0:
            self.convert_dust_to_bnb(assets_to_convert)

    def do_auto_collection(self):
        """
        各种资产归集到杠杆账户上来
        本接口不会将 UM 钱包中的 BNB 资产进行归集
        :return:
        """
        url = f"{self.universe_base_url}/papi/v1/auto-collection"  # 权重(IP): 750  滚动每小时仅能调用500次
        response = self.send_request("POST", url)
        return response.json()

    def do_asset_collection(self, asset):
        """
        特定资产资金归集
        :return:
        """
        params = {'asset': asset}
        url = f"{self.universe_base_url}/papi/v1/asset-collection"  # 权重(IP): 30
        response = self.send_request("POST", url, params=params)
        return response.json()

    def get_account_balance(self, account_type):
        if account_type == 'funding':
            url = f"{self.base_url}/sapi/v1/asset/get-funding-asset"  # 权重(IP): 1
            response = self.send_request("GET", url)
            data = response.json()
            return {item['asset']: float(item['free']) for item in data if float(item['free']) > 0}
        elif account_type == 'margin':
            url = f"{self.base_url}/sapi/v1/margin/account"  # 权重(IP): 10
            response = self.send_request("GET", url)
            data = response.json()
            return {balance['asset']: float(balance['free']) for balance in data['userAssets'] if
                    float(balance['free']) > 0}
        elif account_type == 'futures':
            url = f"{self.futures_base_url}/fapi/v2/balance"  # 权重(IP): 5
            response = self.send_request("GET", url)
            data = response.json()
            balances = {balance['asset']: float(balance['balance']) for balance in data if
                        float(balance['balance']) > 0}
            return balances
        else:  # spot 返回 还有UID的信息
            url = f"{self.base_url}/api/v3/account"  # 权重(IP): 20
            params = {'omitZeroBalances': 'true'}  # 隐藏所有的 0 余额的账户信息
            response = self.send_request("GET", url, params=params)
            data = response.json()
            return {balance['asset']: float(balance['free']) for balance in data['balances'] if
                    float(balance['free']) > 0}

    def get_account_uid(self):
        url = f"{self.base_url}/api/v3/account"  # 权重(IP): 20
        params = {'omitZeroBalances': 'true'}  # 隐藏所有的 0 余额的账户信息
        response = self.send_request("GET", url, params=params)
        if response.status_code != 200:
            logger.warning(response.status_code)
            logger.warning(response.content)
            return -response.status_code  # 返回错误编码
        data = response.json()
        return data['uid']

    def get_account_balance_and_open_positions(self):
        """
        获取合约账户的资产，以及合约信息
        :return: balances, positions
        """
        url = f"{self.universe_base_url}/papi/v1/um/account"  # 权重(IP): 5
        response = self.send_request("GET", url)
        data = response.json()
        # 过滤掉所有数量为 0 的头寸
        # filtered_data = [position for position in data['positions'] if float(position['positionAmt']) != 0.0]
        # return filtered_data
        balances = {asset['asset']: float(asset['crossWalletBalance']) for asset in data['assets'] if
                    float(asset['crossWalletBalance']) > 0}
        positions = data['positions']
        return balances, positions

    def transfer_asset(self, asset, amount, from_account_type, to_account_type):
        """
        万向划转   参考api网址  https://binance-docs.github.io/apidocs/spot/cn/#user_data-14
        :param asset:
        :param amount:
        :param from_account_type:
        :param to_account_type:
        :return:
        """
        url = f"{self.base_url}/sapi/v1/asset/transfer"  # 权重(UID)): 900
        params = {
            'asset': asset,
            'amount': amount,
            'type': f"{from_account_type}_{to_account_type}"
        }
        response = self.send_request("POST", url, params=params)
        if response.status_code == 200:
            logger.info(
                f"Transferred {amount} {asset} from {from_account_type} to {to_account_type}: {response.json()}")
        else:
            logger.error(
                f"Failed to transfer {amount} {asset} from {from_account_type} to {to_account_type}: {response.json()}")

    def calculate_total_unrealized_pnl(self, positions):
        total_unrealized_pnl = 0.0
        for position in positions:
            unrealized_pnl = float(position['unrealizedProfit'])
            total_unrealized_pnl += unrealized_pnl
        return total_unrealized_pnl

    def update_all_balance(self):
        """
        仅仅计算合约账户，以及杠杆账户的总资产量， 对于统一账户而言，这两个账户下的总资产量，决定了仓位
        同时更新用户账户对象，
        """
        total_usdt_value = 0.0
        usdt_balance = 0.0  # USDT 现货的数量
        self.user_account.remove_crypto_asset()
        self.user_account.remove_contract()

        # spot_balances = self.get_account_balance('spot')
        # funding_balances = self.get_account_balance('funding')
        margin_asset_balances = self.get_account_balance('margin')
        future_asset_balances, open_positions = self.get_account_balance_and_open_positions()
        uTime = self.get_server_time()
        # for asset, amount in spot_balances.items():
        #     total_usdt_value += self.get_price_value(asset) * amount
        # for asset, amount in funding_balances.items():
        #     total_usdt_value += self.get_price_value(asset) * amount
        for asset, amount in margin_asset_balances.items():  # 杠杆账户的数字货币资产
            if asset == "USDT":
                usdt_balance += amount
                total_usdt_value += amount
                self.user_account.update_crypto_asset(asset, amount, 1.0, uTime)
            else:
                price = float(memcache_client.get(asset.replace("USDT", "") + 'SwapBid'))
                total_usdt_value += price * amount
                self.user_account.update_crypto_asset(asset, amount, price, uTime)

        for asset, amount in future_asset_balances.items():  # 合约账户的数字货币资产
            if asset == "USDT":  #  TODO 这里不会有合约账户的 usdt 负资产， 那合约账户的 USDT 到底在哪里能查到呢？
                usdt_balance += amount
                total_usdt_value += amount
            else:
                price = float(memcache_client.get(asset.replace("USDT", "") + 'SwapBid'))
                total_usdt_value += price * amount
                self.user_account.update_crypto_asset(asset, amount, price, uTime)

        # 更新 USDT 现货总数
        self.user_account.update_usdt_balance(usdt_balance)

        # 更新合约持仓信息
        for position in open_positions:
            if float(position['positionAmt']) != 0:
                unrealized_pnl = float(position['unrealizedProfit'])
                price = float(memcache_client.get(position['symbol'].replace("USDT", "") + 'SwapBid'))
                self.user_account.update_contract(position['symbol'], position['positionAmt'], price, uTime)

        # 加上未实现盈亏
        total_unrealized_pnl = self.calculate_total_unrealized_pnl(open_positions)
        total_usdt_value += total_unrealized_pnl

        # TODO 这里的计算不准确， 已经通过直接调用接口，来获取用户最真实的所有数据了
        # self.user_account.asset_valuation = total_usdt_value

    def get_symbol_info_spot(self, symbol):
        """
        获取现货  最小交易数量信息
        :param symbol:
        :return:
        """
        if 'USDT' not in symbol:
            symbol = f"{symbol}USDT"
        url = f"{self.base_url}/api/v3/exchangeInfo?symbol={symbol}"  # 权重(IP): 20
        response = requests.get(url)
        logger.info(f"send_request {url} {response.status_code} : {response.content}")
        data = response.json()
        for s in data['symbols']:
            if s['symbol'] == symbol:
                return s
        return None

    def get_symbol_info_swap(self, symbol):
        """
        获取合约  最小交易数量信息
        :param symbol:
        :return:
        """
        if 'USDT' not in symbol:
            symbol = f"{symbol}USDT"
        url = f"{self.futures_base_url}/fapi/v1/exchangeInfo"  # 权重(IP): 1
        response = requests.get(url)
        logger.info(f"send_request {url} {response.status_code} : {response.content}")
        data = response.json()
        for s in data['symbols']:
            if s['symbol'] == symbol:
                return s
        return None

    def get_lot_size(self, symbol, order_type):
        """
        获得每一个币种，合约或者现货的最小下单单位
        :param symbol:  BTC  或者  ETH 这样的
        :param order_type:
        :return:
        """
        lot_size = memcache_client.get(f"lot_size_{order_type}_{symbol}")
        # lot_size = None
        if lot_size is None:
            symbol_info = None
            if order_type == "spot":
                symbol_info = self.get_symbol_info_spot(symbol)
            elif order_type == "swap":
                symbol_info = self.get_symbol_info_swap(symbol)

            if symbol_info is not None:
                for f in symbol_info['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        lot_size = float(f['stepSize'])
                        memcache_client.set(f"lot_size_{order_type}_{symbol}", lot_size, expire=3600)  # 缓存一小时
                        return lot_size

                if lot_size is None:
                    raise ValueError("stepSize not found for symbol")
        else:
            lot_size = float(lot_size)  # memcache 中取出的数据是 byte 格式的
        return lot_size

    def adjust_quantity(self, quantity, step_size):
        """
        根据 step_size 调整 quantity 符合最小下单数量和小数点的要求
        :param quantity:
        :param step_size:
        :return:
        """
        step_size = Decimal(str(step_size))
        quantity = Decimal(str(quantity))
        ret = (quantity // step_size) * step_size
        return float(ret)

    # 非继承接口的函数
    ##########################################################################################

    def do_asset_transfer(self):
        """
        资金划转, 从现货账户和资金账户 把所有资产都转移到杠杆账户中（对于币安统一账户而言，这样最好用）
        :return: None
        """
        # 获取现货账户余额
        spot_balances = self.get_account_balance('spot')
        logger.info("Spot Balances: %s", spot_balances)

        # 获取资金账户余额
        funding_balances = self.get_account_balance('funding')
        logger.info("Funding Balances: %s", funding_balances)

        # 转移现货账户余额
        for asset, amount in spot_balances.items():
            self.transfer_asset(asset, amount, 'MAIN', 'MARGIN')

        # 转移资金账户余额
        for asset, amount in funding_balances.items():
            self.transfer_asset(asset, amount, 'FUNDING', 'MARGIN')

    def set_autoloan(self):
        """设置自动借币（Binance不支持此功能）。"""
        pass

    def set_account_level(self):
        """设置账户模式（Binance不支持此功能）。"""
        pass

    def set_position_mode(self):
        """设置持仓模式（Binance不支持此功能）。"""
        pass

    def get_leverage(self, _ccy):
        """获取杠杆倍数（Binance不支持此功能）。"""
        pass

    def get_leverage_info(self, instId):
        """获取指定杠杆倍数下，相关的预估信息（Binance不支持此功能）。"""
        pass

    def set_leverage(self, _instType, _ccy, _leverage):
        """设置杠杆倍数（Binance不支持此功能）。"""
        pass

    def get_max_size(self, _ccy, isBuy):
        """获取最大可买卖/开仓数量"""
        return 999999999

    def get_market_book_size(self, _ccy, isBuy):
        """获取买卖深度可下单的数量（Binance不支持此功能）。"""
        pass

    def get_order(self, instId, ordId):
        """
        获得订单的状态信息
        :param instId:
        :param ordId:
        :return:
        """
        # url = f"{self.universe_base_url}/papi/v1/margin/order"  TODO 目前仅仅查询合约订单
        url = f"{self.universe_base_url}/papi/v1/um/order"  # 权重(IP): 1
        params = {
            'symbol': f"{instId}USDT",
            'orderId': ordId
        }
        response = self.send_request("GET", url, params=params)
        return response.json()

    def get_income(self, startTime="", endTime="", limit=1000, incomeType="FUNDING_FEE"):
        """
        获取资金流水信息
        :param startTime: 时间戳字符串，可以传输空字符串
        :param endTime: 时间戳字符串，可以传输空字符串
        :param limit: 对多的数据
        :param incomeType: 资金流水类型，如 TRANSFER, REALIZED_PNL, FUNDING_FEE ,  COMMISSION  TODO 交易手续费可能需要实现
        :return: 资金流水信息的 JSON 响应
        """
        url = f"{self.universe_base_url}/papi/v1/um/income"  # 权重: 30
        params = {
            'startTime': startTime,
            'endTime': endTime,
            'limit': limit,
        }
        if incomeType:
            params['incomeType'] = incomeType
        response = self.send_request("GET", url, params=params)
        return response.json()

    def get_account_status(self):
        """
            get_account 接口其实包含了这个接口的信息
             "accountStatus": "NORMAL",  // 统一账户专业版当前账户状态:"NORMAL"正常状态, "MARGIN_CALL"补充保证金, "SUPPLY_MARGIN"再一次补充保证金, "REDUCE_ONLY"触发交易限制, "ACTIVE_LIQUIDATION"手动强制平仓, "FORCE_LIQUIDATION"强制平仓, "BANKRUPTED"破产

        获取 account status
        :return:
        """
        url = f"{self.base_url}/sapi/v1/account/status"  # 权重(IP): 1
        response = self.send_request("GET", url)
        return response.json()

    def get_sub_account_list(self):
        """
        获取 子账户列表
        :return:
        """
        url = f"{self.base_url}/sapi/v1/sub-account/list"  # 权重(IP): 1
        response = self.send_request("GET", url)
        return response.json()

    def get_sub_account_transfer(self):
        """
        查询子账户划转历史 (仅适用子账户)
        :return:
        """
        url = f"{self.base_url}/sapi/v1/sub-account/transfer/subUserHistory"  # 权重(IP): 1
        response = self.send_request("GET", url)
        return response.json()

    def get_margin_interest_history(self, asset="", startTime="", endTime="", size=100, recvWindow=60000):
        """
        获取杠杆利息历史 (USER_DATA)
        :param asset: 资产
        :param startTime: 开始时间戳（毫秒）
        :param endTime: 结束时间戳（毫秒）
        :param size: 每页条数，默认值：10，最大值：100
        :param recvWindow: 请求有效时间，默认值：60000
        :return: 利息历史记录的 JSON 响应
        """
        url = f"{self.universe_base_url}/papi/v1/margin/marginInterestHistory"  # 权重(IP): 1
        params = {'size': size}
        if asset:
            params['asset'] = asset
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime
        response = self.send_request("GET", url, params=params)
        return response.json()

    def get_portfolio_interest_history(self, asset="", startTime="", endTime="", size=100, recvWindow=60000):
        """
        获取统一账户期货负余额利息历史记录
        :param asset: 资产
        :param startTime: 开始时间戳（毫秒）
        :param endTime: 结束时间戳（毫秒）
        :param size: 每页条数，默认值：10，最大值：100
        :param recvWindow: 请求有效时间，默认值：60000
        :return: 利息历史记录的 JSON 响应
        """
        url = f"{self.universe_base_url}/papi/v1/portfolio/interest-history"  # 权重(IP): 50
        params = {'size': size}
        if asset:
            params['asset'] = asset
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime
        response = self.send_request("GET", url, params=params)
        return response.json()

    def get_margin_borrow_repay(self, type="BORROW", startTime="", endTime="", size=100, recvWindow=60000):
        """
        查询借贷/还款记录(USER_DATA)
        :param startTime: 开始时间戳（毫秒）
        :param endTime: 结束时间戳（毫秒）
        :param size: 每页条数，默认值：10，最大值：100
        :param recvWindow: 请求有效时间，默认值：60000
        :return: 利息历史记录的 JSON 响应
        """
        url = f"{self.base_url}/sapi/v1/margin/borrow-repay"  # 权重(IP): 10
        params = {
            'size': size,
            'type': type  # 操作类型：BORROW、REPAY
        }
        if startTime:
            params['startTime'] = startTime
        if endTime:
            params['endTime'] = endTime
        response = self.send_request("GET", url, params=params)
        return response.json()

    def do_margin_borrow_repay(self, asset, amount, type="REPAY"):
        """
        杠杆账户借贷/还款(MARGIN)
        :param asset	STRING	YES
        :param amount	STRING	YES
        :param type	STRING	YES	操作类型：BORROW、REPAY
        :return:
        """
        url = f"{self.base_url}/sapi/v1/margin/borrow-repay"  # 权重(IP): 10
        params = {
            'asset': asset,
            'isIsolated': 'FALSE',  # STRING	YES	是否逐仓杠杆，TRUE, FALSE, 默认 FALSE
            'symbol': asset,  # STRING	YES	逐仓交易对，配合逐仓使用
            'amount': amount,
            'type': type  # 操作类型：BORROW、REPAY
        }
        response = self.send_request("POST", url, params=params)
        return response.json()

    def get_orders_history(self):
        """查看历史订单（Binance不支持此功能）。"""
        pass

    def doOrderSpot(self, instId, sz, side):
        """
        下单现货
        :param instId:
        :param sz:
        :param side:
        :return:
        """
        url = f"{self.universe_base_url}/papi/v1/margin/order"  # 权重(IP): 1
        params = {
            'symbol': f"{instId}USDT",
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': sz,
            'newClientOrderId': f"WA{int(time.time() * 1000)}",  # 系统自动下单的编号
            'recvWindow': 10000,  # 设置 10 秒的时间窗口
        }
        # 调整数量使其符合 stepSize 的要求
        adjusted_quantity = self.adjust_quantity(sz, self.get_lot_size(instId, "spot"))
        params['quantity'] = str(adjusted_quantity)
        logger.info(f"doOrderSpot:{instId}-{side}-{sz}---{params}")
        response = self.send_request("POST", url, params=params)
        if response.status_code == 200:
            logger.info(f"doOrderSpot success:{instId}-{side}-{sz}")
        else:
            logger.info(f"doOrderSpot failed:{instId}-{side}-{sz}")
        return response.status_code, response.json()

    def doOrderSwap(self, instId, sz, side, px=0, reduceOnly="false"):
        """
        下单合约
        :param reduceOnly:   是否是只减仓，仅仅在清空最后仓位的时候，需要传递 字符串 "true"
        :param instId:
        :param sz:
        :param side:
        :return:
        """
        url = f"{self.universe_base_url}/papi/v1/um/order"  # 权重(IP): 1
        params = {
            'symbol': f"{instId}USDT",
            'side': side.upper(),
            'type': 'MARKET',
            'quantity': sz,
            'newClientOrderId': f"WA{int(time.time() * 1000)}",  # 系统自动下单的编号
            'recvWindow': 10000,  # 设置 10 秒的时间窗口
            'reduceOnly': reduceOnly,
        }
        # 调整数量使其符合 stepSize 的要求
        adjusted_quantity = self.adjust_quantity(sz, self.get_lot_size(instId, "swap"))
        params['quantity'] = str(adjusted_quantity)
        logger.info(f"doOrderSwap:{instId}-{side}-{sz}---{params}")
        response = self.send_request("POST", url, params=params)
        if response.status_code == 200:
            logger.info(f"doOrderSwap success:{instId}-{side}-{sz}")
        else:
            logger.info(f"doOrderSwap failed:{instId}-{side}-{sz}")
        time.sleep(30)  # TODO 每次下单都休眠，降低访问频率
        return response.status_code, response.json()

    def make_balance(self, instId, justCheck=False):
        """
        检查货币对的平衡状态，如果失衡，通过平仓降低仓位来实现平衡
        设计初衷，仅仅为了解决小仓位失衡的问题  TODO 有些币种，下单基数有限制，需要考虑（比如 BTC）
        :param justCheck: 仅仅是检查
        :param instId: 货币名称 比如BTC  ETH 等
        :return:
        """
        # 查询现有的合约，以及币的数量
        self.update_all_balance()  # 更新所有资产信息
        num_crypto = self.user_account.get_crypto(instId)  # 现货资产数量
        num_contract = self.user_account.get_contract(instId)  # 合约资产数量
        logger.info(f"make_balance : {instId}")
        logger.info(f"num_crypto = {num_crypto}")
        logger.info(f"num_contract = {num_contract}")

        price = float(memcache_client.get(instId.replace("USDT", "") + 'SwapBid'))
        # 如果这里发现不平衡，则需要通过平掉合约或者现货的仓位，来实现平衡
        diffOfNum = num_crypto + num_contract
        if diffOfNum * price >= 10:  # 合约的空单少了，需要增加空单
            if justCheck:
                return True  # 确实不平衡，需要操作
            self.doOrderSwap(instId, diffOfNum, "sell")
        elif -diffOfNum * price >= 10:  # 现货的多单少了，需要现货补齐
            if justCheck:
                return True  # 确实不平衡，需要操作
            self.doOrderSpot(instId, -diffOfNum, "buy")

    def do_hedge_trade_close(self, instId: str):
        """
        对于单一货币对进行平仓操作
        :param instId:
        :return:
        """
        instId = instId.replace("USDT", "")
        logger.info(f"in do_hedge_trade_close :{instId}")
        # 查询现有的合约，以及币的数量
        self.update_all_balance()  # 更新所有资产信息
        num_crypto = self.user_account.get_crypto(instId)  # 现货资产数量
        num_contract = self.user_account.get_contract(instId)  # 合约资产数量
        logger.info(f"num_crypto = {num_crypto} {instId}")
        logger.info(f"num_contract = {num_contract} {instId}")

        if num_crypto > 0:  # 如果用户有该货币对的现货资产，则将现货资产归集到杠杆账户， 以避免显示资金不足的错误
            self.do_asset_collection(instId)

        if num_crypto >= 0 and num_contract <= 0:  # 只有合约为负数，现货为正数，才能操作  TODO 未来适配一切的
            # 先按照小的来
            close_num = min(abs(num_crypto), abs(num_contract))
            price = float(memcache_client.get(instId + 'SwapBid'))

            lot_size_spot = self.get_lot_size(instId, "spot")
            lot_size_swap = self.get_lot_size(instId, "swap")
            lot_size = max(lot_size_spot, lot_size_swap)  # 获得下单允许的最小数值， 然后取最大值，下单都需要按照这个的整数倍来执行
            while close_num * price > ORDER_USDT_MIN:  #
                logger.info(f"close_num = {close_num} {instId}")
                order_size = self.adjust_quantity(ORDER_USDT_MIN / price, lot_size)
                res_status_code, res_json = self.doOrderSpot(instId, order_size, "sell")  #
                if res_status_code == 200:  # 现货订单成交,才能执行合约订单
                    res_status_code_swap, res_json_swap = self.doOrderSwap(instId, order_size, "buy", reduceOnly="true")  # 清空仓位，需要调用只减仓接口
                    if res_status_code_swap == 200:  # 双腿下单成功，可以进行下一轮操作
                        close_num = close_num - order_size
                    else:  # 单腿警告，现货成交，合约失败了！ 严重错误，需要反思为什么出现了问题
                        logger.warning(f"单腿警告，现货成交，合约失败了！ 严重错误，需要反思为什么出现了问题")
                        return 510
                else:  # 现货订单失败,则尝试资金归集, 再次循环
                    self.do_auto_collection()

            logger.info(f"close_num = {close_num} {instId}")
            # 能运行到这里，剩余的量已经在1倍以内了，直接一次性平掉所有剩余仓位
            self.update_all_balance()  # 更新所有资产信息
            num_crypto = self.user_account.get_crypto(instId)  # 现货资产数量
            num_contract = self.user_account.get_contract(instId)  # 合约资产数量
            # self.do_auto_collection()  # 这里调用资金归集接口， 因为不在大循环中，所以不会超标
            if abs(num_crypto) > 0:
                self.doOrderSpot(instId, abs(num_crypto), "sell")  # 先平仓现货
            if abs(num_contract) > 0:
                self.doOrderSwap(instId, abs(num_contract), "buy", reduceOnly="true")  # 清空仓位，需要调用只减仓接口
            self.do_asset_collection("USDT")
            return 200
        else:
            return 501

    def do_hedge_trade_open(self, money, instId):
        """
        TODO 建仓时间是否需要考虑避开波动性特别强的时间段，  或者每次下单，都需要查询下价格，然后重新定义下单的数量
        根据 money 和 instId， 下单对冲单， 数量以现货订单为基准
        只有 money 大于现货总价值大于 150 USDT 才会执行新的订单
        :param money: USDT金额 一个货币对需要分配到的订单量
        :param instId: 货币名称 比如BTC  ETH 等
        :return: 200 代表正常，其余参见错误代码库
        """
        # 先获得合约的价格，通过价格了解需要完成的目标对冲的总量
        price = float(memcache_client.get(instId + 'SwapBid'))
        totalAimMnt = money / price  # 这里是总量，需要根据合约成数，进行一次取整

        num_crypto_now = self.user_account.get_crypto(instId)  # 现货资产数量
        logger.info(f"num_crypto_now = {num_crypto_now} {instId}")

        needToDoCrypto = totalAimMnt - num_crypto_now  # 需要补足的现货数量
        logger.info(f"needToDoCrypto = {needToDoCrypto} {instId}")

        # TODO 假设所有合约都是 20 倍 杠杆  （杠杆率可调，可以进一步增加钱包余额，但是usdt是否能增加不确定）
        maxCanBuy = self.user_account.usdt_balance / price * 0.95  # 当前剩余USDT现金，最大能买的现货的数量
        logger.info(f"maxCanBuy = {maxCanBuy} {instId}")

        if needToDoCrypto > maxCanBuy:  # 现货无法达到最大下单量， 则按照最大能下单的量来下单
            needToDoCrypto = maxCanBuy
        logger.info(f"needToDoCryptoModifyed = {needToDoCrypto} {instId}")

        if needToDoCrypto < 0:
            logger.warn("下单数量为负数， 已经有足够仓位了，不减仓")
            return 200
        if needToDoCrypto * price < ORDER_USDT_MIN:  # 小于 ORDER_USDT_MIN 美元，则不操作了
            logger.warn("需要补足的订单金额小于特定阈值，不做补偿")
            return 200

        lot_size_spot = self.get_lot_size(instId, "spot")
        lot_size_swap = self.get_lot_size(instId, "swap")
        lot_size = max(lot_size_spot, lot_size_swap)  # 获得下单允许的最小数值， 然后取最大值，下单都需要按照这个的整数倍来执行
        order_size = self.adjust_quantity(ORDER_USDT_MIN / price, lot_size)  # 理论上，单笔 ORDER_USDT_MIN 需要的下单数量
        needToDoCrypto = self.adjust_quantity(needToDoCrypto, lot_size)
        while needToDoCrypto >= lot_size:
            logger.info(f"needToDoCrypto = {needToDoCrypto} {instId}")
            if needToDoCrypto < order_size * 2:  # 如果循环后， 发现需要做的订单已经小于 order_size * 2 了， 则一次性做完
                order_size = needToDoCrypto
                order_size = self.adjust_quantity(order_size, lot_size)
            if needToDoCrypto < order_size:  # 理论上不会走到这里，不过可能会存在一些小数的问题，所以到这里的话，循环直接退出
                break
            res_status_code, res_json = self.doOrderSpot(instId, order_size, "buy")  # 先买现货
            if res_status_code == 200:  # 现货订单成交,才能执行合约订单
                res_status_code_swap, res_json_swap = self.doOrderSwap(instId, order_size, "sell")
                if res_status_code_swap == 200:  # 双腿下单成功，可以进行下一轮操作
                    needToDoCrypto = needToDoCrypto - order_size
                else:  # 单腿警告，现货成交，合约失败了！ 严重错误，需要反思为什么出现了问题
                    memcache_client.set(f"InitAccountStatus_{api_key}", "error", 300)
                    logger.warning(f"单腿警告，现货成交，合约失败了！ 严重错误，需要反思为什么出现了问题")
                    logger.warning(f"one leg waring, do withdraw!")
                    # 回退操作，
                    # self.do_auto_collection()  # 先资金归集，再卖掉刚才买入的现货
                    self.doOrderSpot(instId, order_size, "sell")  #
                    return 510
            else:  # 现货订单失败,则尝试资金归集, 退出
                memcache_client.set(f"InitAccountStatus_{api_key}", "error", 300)
                logger.warning(f"现货下单失败，资金归集后再次尝试")
                logger.warning(f"one leg waring, do withdraw!")
                # self.do_auto_collection()
                return 511

        return 200


def do_init_account(binance_rest_api:BinanceRestAPI):
    # 创建账户前，进行一些基本的 必要的账户操作
    # 下单前 归集 USDT 用于购买现货
    binance_rest_api.do_asset_collection("USDT")

    # 查询，并设置用户持仓方向
    binance_rest_api.user_account.dualSidePosition = binance_rest_api.get_um_position_side()
    if binance_rest_api.user_account.dualSidePosition:
        binance_rest_api.set_um_position_side(False)
        binance_rest_api.user_account.dualSidePosition = False
    binance_rest_api.set_bnbBurn()  # 设置币安币代扣手续费开关

    binance_rest_api.update_account()  # 调用此函数，主要为了获取 asset_valuation 数据  以及账户合约和现货资产

    # 根据剩余 USDT 计算需要新建仓的数量， 购买相应的 BNB 方便手续费对冲   按照手续费千分之一计算，BNB需要购买剩余USDT的千分之一
    price_BNB = float(memcache_client.get('BNB' + 'SwapBid'))
    quantity_BNB = binance_rest_api.user_account.get_crypto("BNB")
    if quantity_BNB * price_BNB < binance_rest_api.user_account.usdt_balance / 1000:
        need_BNB = (binance_rest_api.user_account.usdt_balance / 1000 - quantity_BNB * price_BNB) / price_BNB
        binance_rest_api.doOrderSpot('BNB', need_BNB, 'buy')


    ######################################  建仓相关
    # 根据用户总资产进行建仓资金分配
    totalUSDT = binance_rest_api.user_account.asset_valuation  # 总资产

    fun_ret_code = 200
    for index in range(len(crypto_names)):
        crypto_name = crypto_names[index]
        c_percent = crypto_percent[index]
        if c_percent > 0:
            logger.info(f"{crypto_name}: {c_percent * totalUSDT / 100} USDT")
            # 查询现有的合约，以及币的数量
            binance_rest_api.update_all_balance()  # 更新所有资产信息
            ret_code = binance_rest_api.do_hedge_trade_open(c_percent * totalUSDT / 100, crypto_name)
            if ret_code == 200:
                time.sleep(5)  # TODO 每次下单都休眠，降低访问频率
                pass
            else:  # 下单出现异常情况，退出循环
                fun_ret_code = ret_code
                break
        else:  # 最后一个币  如果是负数百分比 ， 直接传递所有的剩余金额
            binance_rest_api.update_all_balance()
            ret_code = binance_rest_api.do_hedge_trade_open(binance_rest_api.user_account.usdt_balance, crypto_name)
            if ret_code == 200:
                fun_ret_code = ret_code
            else:
                fun_ret_code = ret_code

        # binance_rest_api.do_auto_collection()

    #############################################################  建仓相关
    # 更新用户资产估值
    # binance_rest_api.update_account()

    # 同步用户信息到数据库
    binance_rest_api.user_account.account_state = 1  # 建仓完毕的状态
    update_user_account(binance_rest_api.user_account)  # 更改数据库状态
    return fun_ret_code


def do_close_account(binance_rest_api:BinanceRestAPI):
    # 资产归集，仅仅下单前进行操作
    # binance_rest_api.do_auto_collection()
    binance_rest_api.update_all_balance()  # 更新所有资产信息

    # 根据当前用户的仓位信息，进行对冲平仓
    for contract in binance_rest_api.user_account.contracts:  # 以合约仓位为准，进行平仓
        binance_rest_api.do_hedge_trade_close(contract["name"])
        time.sleep(15)  # TODO 每次下单都休眠，降低访问频率

    # 平仓小额资产到BNB
    # binance_rest_api.do_dust_to_bnb()
    # 更新用户资产估值
    # binance_rest_api.update_account()

    # 同步用户信息到数据库
    binance_rest_api.user_account.account_state = 0  # 未建仓的状态
    update_account_state(binance_rest_api.user_account.uid, binance_rest_api.user_account.account_state)


# 示例用法
if __name__ == "__main__":
    # # jack02
    # api_key = 'I8Z8dTV6aPQ80LEy7P7s3VSidAppKSA2EmhUTCj20XAfaLjRrGcfFsOanzXbddrK'
    # api_secret = '3RR9d2tMSj23PKHMKf583BUI9Jigq4V0GbRXwWU9iwsJgse9DX0LSWptd9oLgxP5'
    # api_key=I8Z8dTV6aPQ80LEy7P7s3VSidAppKSA2EmhUTCj20XAfaLjRrGcfFsOanzXbddrK&api_secret=3RR9d2tMSj23PKHMKf583BUI9Jigq4V0GbRXwWU9iwsJgse9DX0LSWptd9oLgxP5

    # # jack03
    api_key = 'JbExHGJHKVTPYmwmc6YTgghzAzvmtinQbE0q8lN1D4FYKQqfUQddMEnI5QFDo3OG'
    api_secret = 'GKSG3ahQyW9MHWy12FdEyXOdLGZLQLX6C1UiN60OM9L8cVIWi9ssKCnaSSmibHkv'
    # # api_key=JbExHGJHKVTPYmwmc6YTgghzAzvmtinQbE0q8lN1D4FYKQqfUQddMEnI5QFDo3OG&api_secret=GKSG3ahQyW9MHWy12FdEyXOdLGZLQLX6C1UiN60OM9L8cVIWi9ssKCnaSSmibHkv
    #
    # # tangsen
    # api_key = 'bYMGQ4moJjoL1jBauD9aVENWI7O1YAQteLDql1yajTrZFzAoWJsoREA9JLbW5S1D'
    # api_secret = 'CEXHpkEPyNiJZiKjIyLNC82pOIOL1tHLaycCJgLei9i7jqEQJsoUKs65kfERTXbw'
    # # api_key=bYMGQ4moJjoL1jBauD9aVENWI7O1YAQteLDql1yajTrZFzAoWJsoREA9JLbW5S1D&api_secret=CEXHpkEPyNiJZiKjIyLNC82pOIOL1tHLaycCJgLei9i7jqEQJsoUKs65kfERTXbw





    # 为用户创建 BinanceRestAPI 实例
    binance_rest_api = BinanceRestAPI(api_key, api_secret)
    if binance_rest_api.user_account is None:  # 通过获取用户uid 判断 api_key, api_secret 等是否成功
        logger.info(f"User API Key Error")
    logger.info(f"Congratulations! Login successfully, uid = {binance_rest_api.user_account.uid}")

    # # 初始化用户账户, 包含完成初始建仓操作
    do_init_account(binance_rest_api)
    # do_close_account(api_key, api_secret)

    # print(binance_rest_api.set_bnbBurn())
    # binance_rest_api.do_dust_to_bnb()

    # binance_rest_api.doOrderSpot('WIF', 0.997, "sell")

    # binance_rest_api.do_hedge_trade_close("ETH")
    # binance_rest_api.do_hedge_trade_open(190, "BTC")
    # binance_rest_api.do_hedge_trade_open(201, "BTC")
    # binance_rest_api.do_hedge_trade_open(500, "BTC")

    # binance_rest_api.do_asset_collection("USDT")  # 把合约账户上的 USDT 转移到 杠杆账户

    #  查询资金流水
    # print(binance_rest_api.get_income("", ""))

    # 还款 1 美元
    # binance_rest_api.do_margin_borrow_repay('USDT', 1)



    # startTime = int(time.time() * 1000) - 30 * 24 * 60 * 60 * 1000  # 30天前的时间戳
    # endTime = int(time.time() * 1000)  # 当前时间戳
    #
    # # 查询借贷/还款记录(USER_DATA)
    # response = binance_rest_api.get_margin_borrow_repay(type="BORROW", startTime=startTime, endTime=endTime)
    # print(response)
    # response = binance_rest_api.get_margin_borrow_repay(type="REPAY", startTime=startTime, endTime=endTime)
    # print(response)
    # # 获取统一账户期货负余额利息历史记录
    # response = binance_rest_api.get_portfolio_interest_history(startTime=startTime, endTime=endTime)
    # print(response)
    # # 获取杠杆利息历史 (USER_DATA)
    # response = binance_rest_api.get_margin_interest_history(startTime=startTime, endTime=endTime)
    # print(response)

    binance_rest_api.update_account()
    print(binance_rest_api.user_account.compute_crypto_percent())


    # 打印账户概览信息
    logger.info("账户概览：")
    pprint.pprint(binance_rest_api.user_account.get_account_summary())
