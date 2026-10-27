
import json
import threading
import urllib.request
import urllib.error
from unittest.mock import patch

import webhook_idempotency_http as webhook_http

from webhook_metrics import webhook_metrics
from webhook_metrics_alert_pipeline import (
    WebhookMetricsAlertPipeline,
)


server = None
server_thread = None


def send_request(url, result):
    payload = {
        "event_type": "JOB_OUTBOX_FALLBACK_ALERT",
        "alert_id": 944,
    }

    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": "task-92-44",
        },
        method="POST",
    )

    if result == "ERROR":
        mock_result = patch.object(
            webhook_http,
            "process_webhook_event",
            side_effect=RuntimeError("Simulated failure"),
        )
        expected_status = 500
    else:
        mock_result = patch.object(
            webhook_http,
            "process_webhook_event",
            return_value=result,
        )
        expected_status = 200

    with mock_result:
        try:
            with urllib.request.urlopen(
                request,
                timeout=5,
            ) as response:
                actual_status = response.status

        except urllib.error.HTTPError as exc:
            actual_status = exc.code

    assert actual_status == expected_status, (
        actual_status,
        expected_status,
    )


def send_batch(url, processed, errors):
    for _ in range(processed):
        send_request(url, "PROCESSED")

    for _ in range(errors):
        send_request(url, "ERROR")


def check_event(
    pipeline,
    name,
    expected_event,
    expected_status,
    expected_requests,
    expected_errors,
):
    result = pipeline.run()

    assert result["event"] == expected_event, result
    assert result["monitor_status"] == expected_status, result

    window = result["window"]

    assert window["window_requests"] == expected_requests
    assert window["window_errors"] == expected_errors

    print(f"[TEST] {name}= True")


try:
    # 1. 初始化指标
    webhook_metrics.reset()

    pipeline = WebhookMetricsAlertPipeline(
        metrics=webhook_metrics,
        min_requests=10,
        error_threshold=20.0,
    )

    # 2. 启动真实 HTTP Server
    server = webhook_http.create_webhook_server(
        host="127.0.0.1",
        port=0,
    )

    server_thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    server_thread.start()

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/webhook"

    # 3. 首次采样：建立基线
    result = pipeline.run()

    assert result["monitor_status"] == "BASELINE"
    assert result["event"] == "NO_CHANGE"

    print("[TEST] FIRST_BASELINE= True")

    # 4. 第一批：7 成功 + 3 错误
    send_batch(url, processed=7, errors=3)

    check_event(
        pipeline,
        "HTTP_FIRST_ALERT",
        "NEW_ALERT",
        "ALERT",
        10,
        3,
    )

    # 5. 第二批：8 成功 + 2 错误
    send_batch(url, processed=8, errors=2)

    check_event(
        pipeline,
        "HTTP_DUPLICATE_ALERT",
        "DUPLICATE",
        "ALERT",
        10,
        2,
    )

    # 6. 第三批：10 成功 + 0 错误
    send_batch(url, processed=10, errors=0)

    check_event(
        pipeline,
        "HTTP_ALERT_RESOLVED",
        "RESOLVED",
        "OK",
        10,
        0,
    )

    # 7. 检查累计指标
    snapshot = webhook_metrics.snapshot()

    assert snapshot == {
        "processed_total": 25,
        "duplicate_total": 0,
        "conflict_total": 0,
        "error_total": 5,
    }, snapshot

    print("[TEST] FINAL_METRICS_CORRECT= True")

    # 8. 验证最终告警状态
    assert pipeline.current_alert_state() == "NORMAL"

    print("[TEST] FINAL_ALERT_STATE_NORMAL= True")

    # 9. 验证 HTTP 指标查询接口
    metrics_url = f"http://127.0.0.1:{port}/metrics"

    with urllib.request.urlopen(
        metrics_url,
        timeout=5,
    ) as response:
        assert response.status == 200

        http_metrics = json.loads(
            response.read().decode("utf-8")
        )

    assert http_metrics == snapshot

    print("[TEST] HTTP_METRICS_ENDPOINT= True")

    print("[TEST] ALL PASS: Webhook metrics E2E regression")

finally:
    if server is not None:
        server.shutdown()
        server.server_close()

    if server_thread is not None:
        server_thread.join(timeout=5)

    webhook_metrics.reset()
