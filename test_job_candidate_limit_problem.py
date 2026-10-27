
def select_candidates(rows, limit):
    candidates = [
        row for row in rows
        if row["status"] in {
            "FAILED", "TIMEOUT", "RUNNING"
        }
    ]

    candidates.sort(
        key=lambda row: (
            row["updated_at"],
            row["execution_id"],
        ),
        reverse=True,
    )

    return candidates[:limit]


def check(name, condition):
    assert condition, name
    print(f"[TEST] {name}=PASS")


rows = []

# 120 recent RUNNING jobs
for i in range(120):
    rows.append({
        "execution_id": f"RUN-{i:03d}",
        "status": "RUNNING",
        "updated_at": 2000 + i,
    })

# 5 older FAILED jobs
for i in range(5):
    rows.append({
        "execution_id": f"FAIL-{i:03d}",
        "status": "FAILED",
        "updated_at": 1000 + i,
    })

# 300 SUCCESS jobs
for i in range(300):
    rows.append({
        "execution_id": f"OK-{i:03d}",
        "status": "SUCCESS",
        "updated_at": 3000 + i,
    })


result = select_candidates(rows, limit=100)

running_count = sum(
    row["status"] == "RUNNING"
    for row in result
)

failed_count = sum(
    row["status"] == "FAILED"
    for row in result
)

check("TOTAL_ROWS", len(rows) == 425)
check("RESULT_LIMIT", len(result) == 100)
check("RUNNING_COUNT", running_count == 100)
check("FAILED_COUNT", failed_count == 0)
check(
    "FAILED_EXISTS_IN_DATABASE",
    any(row["status"] == "FAILED" for row in rows),
)
check(
    "SUCCESS_EXCLUDED",
    all(row["status"] != "SUCCESS" for row in result),
)

print("[TEST] RUNNING_RETURNED=", running_count)
print("[TEST] FAILED_RETURNED=", failed_count)
print("[TEST] FAILED_MISSED=", 5 - failed_count)
print("[TEST] ALL PASS: Candidate LIMIT Problem")
