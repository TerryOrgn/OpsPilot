
from mysql.connector import errors


# 允许重试的 MySQL 错误码
RETRYABLE_MYSQL_ERRNOS = frozenset({
    2003,  # Can't connect to MySQL server
    2006,  # MySQL server has gone away
    2013,  # Lost connection to MySQL server
    1213,  # Deadlock found
})


def is_retryable_database_error(exc):
    """
    判断数据库异常是否属于可重试故障。

    只做异常分类，不执行重试。
    """

    # 保留 BO-6B 已验证的模拟连接故障
    if isinstance(exc, ConnectionError):
        return True

    # MySQL Connector/Python 的数据库异常
    if isinstance(exc, errors.Error):
        return exc.errno in RETRYABLE_MYSQL_ERRNOS

    return False
