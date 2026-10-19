from alert_manager import resolve_alert

execution_id = "TEST-NOTIFY-002"

result = resolve_alert(
    execution_id,
    "JOB_TIMEOUT",
    "OpsPilot Phase 7 REOPENED通知测试"
)

print(f"[TEST] resolve_alert result: {result}")