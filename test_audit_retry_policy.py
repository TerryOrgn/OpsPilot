
from mysql.connector import errors

from audit_retry_policy import (
    is_retryable_database_error,
)


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


# 1. Python 内置连接异常
check(
    "PYTHON_CONNECTION_ERROR",
    is_retryable_database_error(
        ConnectionError("connection lost")
    ),
)

# 2. MySQL 连接失败
check(
    "MYSQL_CONNECTION_REFUSED",
    is_retryable_database_error(
        errors.InterfaceError(
            errno=2003,
            msg="Can't connect to MySQL",
        )
    ),
)

# 3. MySQL 连接中断
check(
    "MYSQL_SERVER_GONE",
    is_retryable_database_error(
        errors.OperationalError(
            errno=2006,
            msg="MySQL server has gone away",
        )
    ),
)

# 4. MySQL 连接丢失
check(
    "MYSQL_LOST_CONNECTION",
    is_retryable_database_error(
        errors.OperationalError(
            errno=2013,
            msg="Lost connection",
        )
    ),
)

# 5. 数据库死锁
check(
    "MYSQL_DEADLOCK",
    is_retryable_database_error(
        errors.InternalError(
            errno=1213,
            msg="Deadlock found",
        )
    ),
)

# 6. 唯一键冲突不可重试
check(
    "DUPLICATE_KEY_NOT_RETRYABLE",
    not is_retryable_database_error(
        errors.IntegrityError(
            errno=1062,
            msg="Duplicate entry",
        )
    ),
)

# 7. SQL 语法错误不可重试
check(
    "SQL_SYNTAX_NOT_RETRYABLE",
    not is_retryable_database_error(
        errors.ProgrammingError(
            errno=1064,
            msg="SQL syntax error",
        )
    ),
)

# 8. 账号认证失败不可重试
check(
    "AUTH_FAILURE_NOT_RETRYABLE",
    not is_retryable_database_error(
        errors.ProgrammingError(
            errno=1045,
            msg="Access denied",
        )
    ),
)

# 9. 普通 ValueError 不可重试
check(
    "VALUE_ERROR_NOT_RETRYABLE",
    not is_retryable_database_error(
        ValueError("Invalid audit data")
    ),
)

# 10. 未知异常不可重试
check(
    "UNKNOWN_ERROR_NOT_RETRYABLE",
    not is_retryable_database_error(
        RuntimeError("Unexpected failure")
    ),
)

# 11. 未知 MySQL 错误码不可重试
check(
    "UNKNOWN_MYSQL_ERROR_NOT_RETRYABLE",
    not is_retryable_database_error(
        errors.DatabaseError(
            errno=9999,
            msg="Unknown database error",
        )
    ),
)

print("[TEST] ALL PASS: Audit Retry Policy")
