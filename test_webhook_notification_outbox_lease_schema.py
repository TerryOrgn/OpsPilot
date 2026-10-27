
from db import get_connection


TABLE_NAME = "WEBHOOK_NOTIFICATION_OUTBOX"


def get_columns():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COLUMN_NAME,
                    DATA_TYPE,
                    IS_NULLABLE,
                    CHARACTER_MAXIMUM_LENGTH,
                    DATETIME_PRECISION
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                """,
                (TABLE_NAME,),
            )

            rows = cursor.fetchall()

            if rows and not isinstance(rows[0], dict):
                columns = [
                    item[0]
                    for item in cursor.description
                ]

                rows = [
                    dict(zip(columns, row))
                    for row in rows
                ]

            return {
                row["COLUMN_NAME"]: row
                for row in rows
            }

    finally:
        connection.close()


def get_indexes():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    INDEX_NAME,
                    COLUMN_NAME,
                    SEQ_IN_INDEX
                FROM INFORMATION_SCHEMA.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = %s
                ORDER BY INDEX_NAME, SEQ_IN_INDEX
                """,
                (TABLE_NAME,),
            )

            rows = cursor.fetchall()

            if rows and not isinstance(rows[0], dict):
                columns = [
                    item[0]
                    for item in cursor.description
                ]

                rows = [
                    dict(zip(columns, row))
                    for row in rows
                ]

            indexes = {}

            for row in rows:
                indexes.setdefault(
                    row["INDEX_NAME"],
                    [],
                ).append(row["COLUMN_NAME"])

            return indexes

    finally:
        connection.close()


columns = get_columns()
indexes = get_indexes()


# 1. 领取时间字段存在
assert "CLAIMED_AT" in columns
print("[TEST] CLAIMED_AT_EXISTS= True")


# 2. 租约到期时间字段存在
assert "LEASE_EXPIRES_AT" in columns
print("[TEST] LEASE_EXPIRES_AT_EXISTS= True")


# 3. 领取令牌字段存在
assert "CLAIM_TOKEN" in columns
print("[TEST] CLAIM_TOKEN_EXISTS= True")


# 4. 时间字段类型正确
for name in (
    "CLAIMED_AT",
    "LEASE_EXPIRES_AT",
):
    column = columns[name]

    assert column["DATA_TYPE"].lower() == "datetime"
    assert column["DATETIME_PRECISION"] == 6

print("[TEST] DATETIME_PRECISION_CORRECT= True")


# 5. Token 字段类型正确
token_column = columns["CLAIM_TOKEN"]

assert token_column["DATA_TYPE"].lower() == "varchar"
assert token_column["CHARACTER_MAXIMUM_LENGTH"] == 64

print("[TEST] CLAIM_TOKEN_TYPE_CORRECT= True")


# 6. 新字段均允许 NULL
for name in (
    "CLAIMED_AT",
    "LEASE_EXPIRES_AT",
    "CLAIM_TOKEN",
):
    assert columns[name]["IS_NULLABLE"] == "YES"

print("[TEST] NULLABLE_FOR_COMPATIBILITY= True")


# 7. 租约索引存在且顺序正确
assert indexes.get("IDX_OUTBOX_LEASE") == [
    "STATUS",
    "LEASE_EXPIRES_AT",
]

print("[TEST] LEASE_INDEX_CORRECT= True")


# 8. 原有主键和唯一索引保留
assert indexes.get("PRIMARY") == ["ID"]
assert indexes.get("UK_OUTBOX_EVENT_ID") == [
    "EVENT_ID"
]

print("[TEST] ORIGINAL_KEYS_PRESERVED= True")


print("[INFO] LEASE_COLUMNS=", {
    name: columns[name]["DATA_TYPE"]
    for name in (
        "CLAIMED_AT",
        "LEASE_EXPIRES_AT",
        "CLAIM_TOKEN",
    )
})

print(
    "[TEST] ALL PASS: "
    "Webhook notification outbox lease schema"
)
