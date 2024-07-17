# RestAPI.py
from abc import ABC, abstractmethod

class RestAPI(ABC):
    """REST API接口定义，包含所有需要实现的方法。"""
    @abstractmethod
    def send_request(self, method, endpoint, params, data=None):
        """
        发送http请求，获得response的封装函数
        :param method:   GET，或者 POST
        :param endpoint:  URL 地址
        :param params:
        :param data:
        :return:
        """
        pass


    @abstractmethod
    def update_account(self):
        """
        获取账户配置信息，并更新信息到用户账户。
        :return: 响应数据
        """
        pass

    @abstractmethod
    def set_autoloan(self):
        """
        设置自动借币。
        :return: None
        """
        pass

    @abstractmethod
    def set_account_level(self):
        """
        设置账户模式。
        账户模式的首次设置，需要在网页或手机app上进行。
        :return: None
        """
        pass

    @abstractmethod
    def set_position_mode(self):
        """
        设置持仓模式。
        :return: None
        """
        pass

    @abstractmethod
    def get_leverage(self, _ccy):
        """
        获取杠杆倍数。
        :param _ccy: 币种
        :return: None
        """
        pass

    @abstractmethod
    def get_leverage_info(self, instId):
        """
        获取指定杠杆倍数下，相关的预估信息。
        :param instId: 交易对ID
        :return: 最大允许杠杆倍数
        """
        pass

    @abstractmethod
    def set_leverage(self, _instType, _ccy, _leverage):
        """
        设置杠杆倍数。
        :param _instType: 类型（MARGIN或SWAP）
        :param _ccy: 币种
        :param _leverage: 杠杆倍数
        :return: None
        """
        pass

    @abstractmethod
    def get_max_size(self, _ccy, isBuy):
        """
        获取最大可买卖/开仓数量。
        :param _ccy: 币种
        :param isBuy: 是否是买
        :return: 最大数量
        """
        pass

    @abstractmethod
    def get_market_book_size(self, _ccy, isBuy):
        """
        获取买卖深度可下单的数量（买1或者卖1的数量）。
        :param _ccy: 币种
        :param isBuy: 是否是买
        :return: 可下单数量
        """
        pass

    @abstractmethod
    def do_asset_transfer(self):
        """
        资金划转。
        :return: None
        """
        pass

    @abstractmethod
    def get_order(self, instId, ordId):
        """
        查看特定订单情况。
        :param instId: 交易对ID
        :param ordId: 订单ID
        :return: 订单信息
        """
        pass

    @abstractmethod
    def get_orders_history(self):
        """
        查看历史订单。
        :return: 历史订单信息
        """
        pass

    @abstractmethod
    def doOrderSpot(self, instId, sz, side):
        """
        市场价下单（现货）。
        :param instId: 交易对ID
        :param sz: 下单数量
        :param side: 方向（买或卖）
        :return: 是否下单成功
        """
        pass

    @abstractmethod
    def doOrderSwap(self, instId, sz, side, px=0):
        """
        挂单下单（合约）。
        :param instId: 交易对ID
        :param sz: 下单数量
        :param side: 方向（买或卖）
        :param px: 价格（大于0为限价单，否则为市价单）
        :return: 订单ID
        """
        pass

    @abstractmethod
    def make_balance(self, instId, size=1, justCheck=False):
        """
        检查货币对的平衡状态，如果失衡，通过平仓降低仓位来实现平衡。
        :param instId: 交易对ID
        :param size: 检查平衡的倍数
        :param justCheck: 仅检查是否平衡
        :return: None
        """
        pass

    @abstractmethod
    def do_hedge_trade_open(self, money, instId):
        """
        实现单货币对冲，完成某一货币的完全对冲。
        :param money: USDT金额
        :param instId: 交易对ID
        :return: 剩余未执行数量（正数表示剩余，0表示操作完毕，负数表示异常）
        """
        pass

