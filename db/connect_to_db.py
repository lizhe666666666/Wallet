import mysql.connector
from datetime import datetime
from config import db_config


def connect_to_db(config):
    """
    连接到MySQL数据库的函数
    :param config:
    :return:
    """
    try:
        cnx = mysql.connector.connect(**config)
        return cnx
    except mysql.connector.Error as err:
        print(f"数据库错误 DB error: {err}")
        return None



def insert_sample_record():
    # 连接到数据库
    cnx = connect_to_db(db_config)
    if not cnx:
        print("Failed to connect to the database.")
        return

    cursor = cnx.cursor()

    # 定义插入查询
    insert_query = """
    INSERT INTO funding_fee (uid, ts, symbol, income)
    VALUES (%s, %s, %s, %s)
    """

    # 示例数据
    uid = "12345"
    ts = datetime.utcnow()
    symbol = "BTCUSDT"
    income = 0.01

    # 执行插入查询
    try:
        cursor.execute(insert_query, (uid, ts, symbol, income))
        cnx.commit()
        print("Record inserted successfully.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        cursor.close()
        cnx.close()

if __name__ == "__main__":
    insert_sample_record()
