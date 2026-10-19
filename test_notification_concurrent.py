from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from notification_claim import claim_notifications


TEST_TYPE = "CONSOLE_TEST_CONCURRENT"

# 两个线程在同一个起点开始领取
barrier = Barrier(2)


def worker(worker_name):
    print(f"[{worker_name}] 准备领取")

    barrier.wait(timeout=10)

    notifications = claim_notifications(
        limit=1,
        notification_type=TEST_TYPE
    )

    ids = [
        item["NOTIFICATION_ID"]
        for item in notifications
    ]

    print(f"[{worker_name}] 领取结果: {ids}")

    return ids


def main():
    print("[TEST] 开始双 Dispatcher 并发领取测试")

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(worker, "Dispatcher-A")
        future_b = executor.submit(worker, "Dispatcher-B")

        result_a = future_a.result()
        result_b = future_b.result()

    all_ids = result_a + result_b

    print(f"\n[TEST] Dispatcher-A: {result_a}")
    print(f"[TEST] Dispatcher-B: {result_b}")
    print(f"[TEST] 合计领取数量: {len(all_ids)}")

    assert len(all_ids) == 1, (
        f"并发领取数量异常: {all_ids}"
    )

    assert len(set(all_ids)) == 1, (
        f"通知 ID 异常: {all_ids}"
    )

    print("[TEST] PASS：两个 Dispatcher 合计领取 1 条通知")


if __name__ == "__main__":
    main()