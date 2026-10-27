
from webhook_request_hash import calculate_request_hash


payload_a = {
    "alert_id": 1001,
    "status": "FAILED",
}

payload_b = {
    "status": "FAILED",
    "alert_id": 1001,
}

payload_c = {
    "alert_id": 1001,
    "status": "SUCCESS",
}


# 1. 相同内容，不同字段顺序
hash_a = calculate_request_hash(payload_a)
hash_b = calculate_request_hash(payload_b)

assert hash_a == hash_b
print("[TEST] SAME_CONTENT_SAME_HASH= True")


# 2. 不同内容
hash_c = calculate_request_hash(payload_c)

assert hash_a != hash_c
print("[TEST] DIFFERENT_CONTENT_DIFFERENT_HASH= True")


# 3. SHA-256 输出长度
assert len(hash_a) == 64
print("[TEST] HASH_LENGTH_64= True")


# 4. 多次计算结果稳定
assert calculate_request_hash(payload_a) == hash_a
print("[TEST] HASH_DETERMINISTIC= True")


# 5. 嵌套 JSON 字段顺序不同
nested_a = {
    "alert_id": 1001,
    "details": {
        "old_status": "NORMAL",
        "new_status": "FAILED",
    },
}

nested_b = {
    "details": {
        "new_status": "FAILED",
        "old_status": "NORMAL",
    },
    "alert_id": 1001,
}

assert (
    calculate_request_hash(nested_a)
    == calculate_request_hash(nested_b)
)

print("[TEST] NESTED_JSON_SAME_HASH= True")


print("[TEST] ALL PASS: SHA256 request hash")
