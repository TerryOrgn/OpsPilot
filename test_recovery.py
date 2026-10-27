from notification_recovery import recover_stale_notifications

recovered_count = recover_stale_notifications(
    notification_type="CONSOLE_TEST_RECOVERY_E2E"
)

assert recovered_count == 1, (
    f"预期恢复 1 条通知，实际恢复 {recovered_count} 条"
)

print("[TEST] PASS：Recovery 成功恢复 ID=22")