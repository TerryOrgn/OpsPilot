
import json
import threading
import urllib.request
import urllib.error

from webhook_idempotency_http import create_webhook_server
from webhook_metrics import webhook_metrics


server = None
server_thread = None

try:
    # 1. 初始化测试指标
    webhook_metrics.reset()

    webhook_metrics.record("PROCESSED")
    webhook_metrics.record("PROCESSED")
    webhook_metrics.record("DUPLICATE")
    webhook_metrics.record("CONFLICT")

    expected = {
        "processed_total": 2,
        "duplicate_total": 1,
        "conflict_total": 1,
        "error_total": 0,
    }

    # 2. 启动真实 HTTP Server
    server = create_webhook_server(
        host="127.0.0.1",
        port=0,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    server_thread.start()

    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"

    # 3. 验证 GET /metrics
    with urllib.request.urlopen(
        f"{base_url}/metrics",
        timeout=5,
    ) as response:
        assert response.status == 200

        content_type = response.headers.get(
            "Content-Type"
        )
        assert content_type == "application/json"

        body = json.loads(
            response.read().decode("utf-8")
        )

    assert body == expected, body

    print("[TEST] METRICS_HTTP_200= True")
    print("[TEST] METRICS_JSON_CORRECT= True")

    # 4. 验证 GET 不会修改计数器
    assert webhook_metrics.snapshot() == expected

    print("[TEST] METRICS_READ_ONLY= True")

    # 5. 验证不存在的路径返回 404
    try:
        urllib.request.urlopen(
            f"{base_url}/unknown",
            timeout=5,
        )
        raise AssertionError(
            "Unknown path must return HTTP 404"
        )

    except urllib.error.HTTPError as exc:
        assert exc.code == 404, exc.code

    print("[TEST] UNKNOWN_PATH_404= True")

    # 6. 再次查询，确认计数未变化
    with urllib.request.urlopen(
        f"{base_url}/metrics",
        timeout=5,
    ) as response:
        second_body = json.loads(
            response.read().decode("utf-8")
        )

    assert second_body == expected

    print("[TEST] METRICS_STABLE= True")
    print("[TEST] ALL PASS: Metrics HTTP endpoint")

finally:
    if server is not None:
        server.shutdown()
        server.server_close()

    if server_thread is not None:
        server_thread.join(timeout=5)

    webhook_metrics.reset()
