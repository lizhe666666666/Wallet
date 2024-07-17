import logging

from pymemcache.client import base

# 创建一个新的日志记录器
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# 创建访问日志处理器
access_handler = logging.FileHandler("access1.log")
access_handler.setLevel(logging.INFO)  # 记录INFO及以上级别的日志
access_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
# 创建错误日志处理器
error_handler = logging.FileHandler("error1.log")
error_handler.setLevel(logging.ERROR)  # 记录ERROR及以上级别的日志
error_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
# 创建控制台日志处理器
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # 记录DEBUG及以上级别的日志
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

# 将处理器添加到日志记录器
logger.addHandler(access_handler)
logger.addHandler(error_handler)
logger.addHandler(console_handler)

# 定义环境变量，可以是 "production", "test", "development"
# ENVIRONMENT = "production"
ENVIRONMENT = "development"
# ENVIRONMENT = "test"


proxy_url = ""

if ENVIRONMENT == "production":  # 线上正式环境
    memcache_client = base.Client(('127.0.0.1', 11211))
    db_config = {
        'user': 'root',
        'password': 'daicash@ng123',
        'host': '127.0.0.1',
        'database': 'wallet',
    }
elif ENVIRONMENT == "test":  # 线上测试环境
    memcache_client = base.Client(('127.0.0.1', 11212))
    db_config = {
        'user': 'root',
        'password': 'daicash@ng123',
        'host': '127.0.0.1',
        'database': 'wallet_test',
    }
elif ENVIRONMENT == "development":  # 台式机开发环境
    proxy_url = "http://w.ixinfeng.com:81/proxy"  # 这个方法失败了，不去浪费时间了
    memcache_client = base.Client(('101.32.221.157', 11212))
    db_config = {
        'user': 'wallet_user',
        'password': 'Li573226',
        'host': '101.32.221.157',
        'database': 'wallet_test',
    }

else:
    raise ValueError("Invalid environment specified")

#############################################################

# 精选出来的货币对
crypto_names_price = ["BTC", "ETH", "JUP", "STX", "FIL", "ARB", "OP", "MKR", "LDO", "FET", "RNDR", "WIF", "BNB", "CFX", "SUI", "KEY", "ETC", "FTM"]  # 最新更新的靠谱表格
crypto_names = ["WIF", "LDO", "MKR", "OP", "ARB", "FIL", "FET", "ETC", "FTM"]
crypto_percent = ["15.00", "10.60", "9.99", "9.82", "9.53", "9.50", "9.42", "8.73", "8.32"]  # -1 代表最后一个币 要根据剩余USDT来动态建仓

# TODO 重建， 根据最新配置，先执行平仓，平仓仓位大于现有的，再重新调用建仓函数即可

# 建仓基本单位
ORDER_USDT_MIN = 200  # 建仓或者平仓的最小金额， 小步快跑方式建仓， 避免大订单， 拿到不好的价格

# memcache_client.set(f"test", 1)
# abc = memcache_client.get(f"test")
# print(abc)
