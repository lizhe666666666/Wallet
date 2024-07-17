import time

from config import db_config, logger
from db.connect_to_db import connect_to_db


def update_user_account(user_account):
    """
    更新用户账户记录，如果没有记录则插入新的记录。
    :param user_account: 用户账户对象
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logger.error("Failed to connect to the database.")
        return

    cursor = cnx.cursor()

    query = """
    INSERT INTO user_account (uid, last_update_ts, api_key, api_secret, account_state, asset_valuation, usdt_balance, margin_rate)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
    last_update_ts = VALUES(last_update_ts),
    api_key = VALUES(api_key),
    api_secret = VALUES(api_secret),
    account_state = VALUES(account_state),
    asset_valuation = VALUES(asset_valuation),
    usdt_balance = VALUES(usdt_balance),
    margin_rate = VALUES(margin_rate)
    """
    cursor.execute(query, (
        user_account.uid,
        int(time.time()),
        user_account.api_key,
        user_account.secret_key,
        user_account.account_state,
        user_account.asset_valuation,
        user_account.usdt_balance,
        user_account.margin_rate
    ))

    cnx.commit()
    cursor.close()
    cnx.close()


def get_user_accounts():
    """
    获取所有用户账户记录。
    :return: 用户账户对象列表
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logger.error("Failed to connect to the database.")
        return []

    cursor = cnx.cursor()

    query = "SELECT uid, api_key, api_secret, account_state, asset_valuation, usdt_balance, margin_rate FROM user_account"
    cursor.execute(query)
    result = cursor.fetchall()

    user_accounts = []
    from UserAccount import UserAccount
    for row in result:
        user_account = UserAccount(0, row[1], row[2])
        user_account.uid = row[0]
        user_account.account_state = row[3]
        user_account.asset_valuation = row[4]
        user_account.usdt_balance = row[5]
        user_account.margin_rate = row[6]
        user_accounts.append(user_account)

    cursor.close()
    cnx.close()

    return user_accounts


def update_account_state(uid, new_state):
    """
    通过 uid 更新 account_state，成功返回1，失败返回0
    :param uid: 用户 ID
    :param new_state: 新的账户状态
    :return: 成功返回 1，失败返回 0
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logger.error("Failed to connect to the database.")
        return 0

    cursor = cnx.cursor()

    query = "UPDATE user_account SET account_state = %s WHERE uid = %s"
    cursor.execute(query, (new_state, uid))
    cnx.commit()

    updated_rows = cursor.rowcount

    cursor.close()
    cnx.close()

    return 1 if updated_rows > 0 else 0


def get_user_account_by_uid(uid):
    """
    通过 uid 查找 user_account 对象，成功返回 user_account对象，失败返回 None
    :param uid: 用户 ID
    :return: 成功返回 user_account对象，失败返回 None
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logger.error("Failed to connect to the database.")
        return None

    cursor = cnx.cursor()

    query = "SELECT uid, api_key, api_secret, account_state, asset_valuation, usdt_balance, margin_rate FROM user_account WHERE uid = %s"
    cursor.execute(query, (uid,))
    result = cursor.fetchone()

    from UserAccount import UserAccount
    if result:
        user_account = UserAccount(0, result[1], result[2])
        user_account.uid = result[0]
        user_account.account_state = result[3]
        user_account.asset_valuation = result[4]
        user_account.usdt_balance = result[5]
        user_account.margin_rate = result[6]
    else:
        user_account = None

    cursor.close()
    cnx.close()

    return user_account


def get_user_account_by_api_key(api_key, api_secret):
    """
    通过 api_key 查找 user_account 对象，成功返回 user_account对象，失败返回 None
    :param api_key: 用户 api_key
    :param api_secret: 用户 api_secret
    :return: 成功返回 user_account对象，失败返回 None
    """
    cnx = connect_to_db(db_config)
    if not cnx:
        logger.error("Failed to connect to the database.")
        return None

    cursor = cnx.cursor()
    # query = f"SELECT uid, api_key, api_secret, account_state, asset_valuation, usdt_balance, margin_rate FROM user_account WHERE api_key='{api_key}' AND api_secret='{api_secret}'"
    # print(query)
    query = "SELECT uid, api_key, api_secret, account_state, asset_valuation, usdt_balance, margin_rate FROM user_account WHERE api_key=%s and api_secret=%s"
    # logger.info(f"Executing query: {query} with api_key: {api_key} and api_secret: {api_secret}")

    cursor.execute(query, (api_key, api_secret,))
    result = cursor.fetchone()

    from UserAccount import UserAccount
    if result:
        user_account = UserAccount(0, result[1], result[2])
        user_account.uid = result[0]
        user_account.account_state = result[3]
        user_account.asset_valuation = result[4]
        user_account.usdt_balance = result[5]
        user_account.margin_rate = result[6]
    else:
        user_account = None

    cursor.close()
    cnx.close()

    return user_account


if __name__ == "__main__":
    from UserAccount import UserAccount

    # api_key = 'JbExHGJHKVTPYmwmc6YTgghzAzvmtinQbE0q8lN1D4FYKQqfUQddMEnI5QFDo3OG'
    # api_secret = 'GKSG3ahQyW9MHWy12FdEyXOdLGZLQLX6C1UiN60OM9L8cVIWi9ssKCnaSSmibHkv'

    api_key = 'bYMGQ4moJjoL1jBauD9aVENWI7O1YAQteLDql1yajTrZFzAoWJsoREA9JLbW5S1D'
    api_secret = 'CEXHpkEPyNiJZiKjIyLNC82pOIOL1tHLaycCJgLei9i7jqEQJsoUKs65kfERTXbw'

    user_account = get_user_account_by_api_key(api_key, api_secret)
    if user_account:
        print(f"Found user account: UID: {user_account.uid}, Account State: {user_account.account_state}")
    else:
        print("User account not found")

    # 示例用法
    # 创建一个示例用户账户对象
    example_user_account = UserAccount(0, "example_api_key", "example_secret_key")
    example_user_account.uid = "123456"
    example_user_account.account_state = 1
    example_user_account.asset_valuation = 100000
    example_user_account.usdt_balance = 5000
    example_user_account.margin_rate = 10

    # 更新用户账户记录
    update_user_account(example_user_account)

    # 获取所有用户账户记录
    accounts = get_user_accounts()
    for account in accounts:
        print(f"UID: {account.uid}, API Key: {account.api_key}, Account State: {account.account_state}")

    # 更新特定用户的账户状态
    update_result = update_account_state("123456", 0)
    print(f"Update account state result: {update_result}")

    # 通过 UID 获取用户账户对象
    user_account = get_user_account_by_uid("123456")
    if user_account:
        print(f"Found user account: UID: {user_account.uid}, Account State: {user_account.account_state}")
    else:
        print("User account not found")


