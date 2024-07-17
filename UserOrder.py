class UserOrder:

    def __init__(self, _orderId, _instType, _instId, _state, _accFillSz):
        """
        订单类，初始化
        :param _orderId:
        :param _instType:
        :param _instId:
        :param _state:
        :param _accFillSz:
        """
        self.orderId = _orderId
        self.instType = _instType
        self.instId = _instId
        self.state = _state
        self.accFillSz = int(_accFillSz)
