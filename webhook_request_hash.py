
import hashlib
import json


def calculate_request_hash(payload: dict) -> str:
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()
