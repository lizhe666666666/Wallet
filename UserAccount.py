from datetime import datetime

from config import crypto_names
from db.get_user_account import get_user_account_by_uid


class UserAccount:
    def __init__(self, _uid, _api_key, _secret_key, _passphrase=""):
        """
        初始化用户账户。
        :param _uid:
        :param _api_key:
        :param _secret_key:
        :param _passphrase:  非必须参数，只有okx 需要传递
        """
        self.uid = _uid  # 当前请求的账户ID，账户uid和app上的一致
        self.api_key = _api_key
        self.secret_key = _secret_key

        ##############################################################################################
        #  binance 设置独享
        self.accountStatus = ''  # 统一账户账户状态："NORMAL", "MARGIN_CALL", "SUPPLY_MARGIN", "REDUCE_ONLY", "ACTIVE_LIQUIDATION", "FORCE_LIQUIDATION", "BANKRUPTED"
        self.dualSidePosition = True  # True: 双向持仓模式；False: 单向持仓模式
        #  binance 设置独享
        ##############################################################################################

        self.asset_valuation = 0  # 用户的资产总估值
        self.usdt_balance = 0  # 用户的USDT余额（这个金额如果小于0，下单现货就需要借贷了）
        self.crypto_assets = []  # 用户持有的加密货币资产列表 （不包含 USDT）
        self.contracts = []  # 用户持有的合约列表
        self.margin_rate = 0  # 账户的保证金率
        self.account_state = 0  # 账户状态， 1 代表正在运行，已建仓   0，代表账户策略停止

    def update_crypto_asset(self, name, quantity, current_price, uTime):
        """
        更新或添加一个加密货币资产到账户。
        :param name: 加密货币的名称。
        :param quantity: 持有的加密货币数量。
        :param current_price: 加密货币当前的价格。
        :param uTime: 更新时间。
        """
        for asset in self.crypto_assets:
            if asset["name"] == name:
                asset["quantity"] = float(quantity)
                asset["current_price"] = current_price
                asset["money"] = quantity * current_price
                asset["uTime"] = uTime
                break
        else:
            self.crypto_assets.append({"name": name, "quantity": quantity, "current_price": current_price, "money": quantity * current_price, "uTime": uTime})

    def update_contract(self, name, quantity, current_price, uTime):
        """
        更新或添加一个合约到账户。
        :param name: 合约的名称。
        :param quantity: 持有的合约数量。
        :param current_price: 合约当前的价格。
        :param uTime: 更新时间。
        """
        for contract in self.contracts:
            if contract["name"] == name:
                contract["quantity"] = float(quantity)
                contract["current_price"] = current_price
                contract["uTime"] = uTime
                break
        else:
            self.contracts.append({"name": name, "quantity": float(quantity), "current_price": current_price, "uTime": uTime})

    def remove_crypto_asset(self):
        """
        删除所有加密货币资产信息
        """
        self.crypto_assets = []

    def remove_contract(self):
        """
        删除所有合约信息
        """
        self.contracts = []

    def update_assert_valuation(self, valuation):
        self.asset_valuation = valuation

    def update_usdt_balance(self, balance):
        """
        更新USDT余额。
        :param balance: 最新金额。
        """
        self.usdt_balance = balance

    def update_margin_rate(self, new_rate):
        """
        更新账户的保证金率。
        :param new_rate: 新的保证金率。
        """
        self.margin_rate = new_rate

    def get_account_summary(self):
        """
        获取账户概览信息。
        :return: 返回一个字典，包含USDT余额、加密货币资产、合约列表和保证金率。
        """
        initial_capital = 0  # 用户的初始本金数据
        db_user_account = get_user_account_by_uid(self.uid)
        if db_user_account is None:
            initial_capital = db_user_account.asset_valuation
        else:
            initial_capital = self.asset_valuation

        asset_total = 0
        for asset in self.crypto_assets:
            if asset["name"] != 'USDT':
                asset_total += asset["money"]
        return {
            "initial_capital": initial_capital,
            "asset USDT Balance": self.asset_valuation,
            "asset Total": asset_total,
            "USDT Balance": self.usdt_balance,
            "Margin Rate": self.margin_rate,
            "Account Status": self.accountStatus,
            "DualSide Position": self.dualSidePosition,
            "Crypto Assets": self.crypto_assets,
            "Contracts": self.contracts,
        }

    def get_crypto(self, ccy):
        """
        获得特定加密货币的数量
        :param ccy:
        :return:
        """
        for asset in self.crypto_assets:
            if ccy in asset["name"]:
                return asset["quantity"]
        return 0

    def get_contract(self, ccy):
        """
        获得特定合约的数量
        :param ccy:
        :return:
        """
        for contract in self.contracts:
            if ccy in contract["name"]:
                return contract["quantity"]
        return 0

    def compute_crypto_percent(self):
        """
        根据加密货币列表的资产金额，返回每种加密货币的总资金金额占比
        对冲情况等
        :return:
        """
        totalMoney = sum(asset["money"] for asset in self.crypto_assets)

        # 创建合约字典，以便快速查找
        contract_dict = {contract["name"]: contract for contract in self.contracts}

        account_view = []
        for asset in self.crypto_assets:
            hedge_quantity = asset["quantity"]
            current_price = asset["current_price"]
            contract = contract_dict.get(asset["name"])
            if contract:
                hedge_quantity += contract["quantity"]
                current_price = contract["current_price"]

            account_view.append(
                {
                    "name": asset["name"],
                    "percent": asset["money"] / totalMoney * 100,
                    "money": asset["money"],
                    "quantity": asset["quantity"],
                    "hedge_quantity": hedge_quantity,
                    "hedge_money": hedge_quantity * current_price,
                    "current_price": current_price,
                    "totalMoney": totalMoney
                }
            )

        # 按百分比降序排序
        account_view_sorted = sorted(account_view, key=lambda x: x["percent"], reverse=True)

        return account_view_sorted

