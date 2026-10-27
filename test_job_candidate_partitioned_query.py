
STATUSES = ("FAILED", "TIMEOUT", "RUNNING")


def select_by_status(rows, status, limit):
    candidates = [
        row for row in rows
        if row["status"] == status
    ]

    candidates.sort(
        key=lambda row: (
            row["updated_at"],
            row["execution_id"],
        ),
        reverse=True,
    )

    return candidates[:limit]


def select_partitioned(rows, per_status_limit=100):
    merged = []

    for status in STATUSES:
        merged.extend(
            select_by_status(
                rows,
                status,
                per_status_limit,
            )
        )

    merged.sort(
        key=lambda row: (
            row["updated_at"],
            row["execution_id"],
        ),
        reverse=True,
    )

    return merged


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


rows = []

for i in range(120):
    rows.append({
        "execution_id": f"RUN-{i:03d}",
        "status": "RUNNING",
        "updated_at": 2000 + i,
    })

for i in range(5):
    rows.append({
        "execution_id": f"FAIL-{i:03d}",
        "status": "FAILED",
        "updated_at": 1000 + i,
    })

for i in range(300):
    rows.append({
        "execution_id": f"OK-{i:03d}",
        "status": "SUCCESS",
        "updated_at": 3000 + i,
    })


result = select_partitioned(rows)

running_count = sum(
    row["status"] == "RUNNING"
    for row in result
)

failed_count = sum(
    row["status"] == "FAILED"
    for row in result
)

check("TOTAL_ROWS", len(rows) == 425)
check("PARTITIONED_COUNT", len(result) == 105)
check("RUNNING_COUNT", running_count == 100)
check("FAILED_COUNT", failed_count == 5)
check(
    "SUCCESS_EXCLUDED",
    all(row["status"] != "SUCCESS" for row in result),
)
check(
    "ORDER_PRESERVED",
    all(
        result[i]["updated_at"]
        >= result[i + 1]["updated_at"]
        for i in range(len(result) - 1)
    ),
)
check(
    "NO_DUPLICATE_EXECUTIONS",
    len({
        row["execution_id"]
        for row in result
    }) == len(result),
)

print("[TEST] RUNNING_RETURNED=", running_count)
print("[TEST] FAILED_RETURNED=", failed_count)
print("[TEST] TOTAL_CANDIDATES=", len(result))
print("[TEST] ALL PASS: Partitioned Candidate Query")
