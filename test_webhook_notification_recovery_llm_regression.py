
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


TEST_FILES = [
    (
        "AQ_AGENT_REGRESSION",
        "test_webhook_notification_recovery_agent_regression.py",
        None,
    ),
    (
        "AR_TOOL_DEFINITION",
        "test_webhook_notification_recovery_llm_definition.py",
        8,
    ),
    (
        "AR_MOCK_RESPONSES",
        "test_webhook_notification_recovery_llm_mock.py",
        12,
    ),
    (
        "AS_SAFE_AGENT",
        "test_webhook_notification_recovery_llm_safe_agent.py",
        14,
    ),
    (
        "AT_BOUNDARY",
        "test_webhook_notification_recovery_llm_safe_agent_boundary.py",
        14,
    ),
    (
        "AU_OBSERVABILITY",
        "test_webhook_notification_recovery_agent_observability.py",
        15,
    ),
    (
        "AW_TRACE_CONTEXT",
        "test_webhook_notification_recovery_trace_context.py",
        15,
    ),
    (
        "AX_TRACE_CONCURRENCY",
        "test_webhook_notification_recovery_trace_concurrency.py",
        16,
    ),
]


def run_suite(name, filename, expected_count):
    path = BASE_DIR / filename

    if not path.is_file():
        return {
            "name": name,
            "passed": False,
            "reason": "FILE_MISSING",
        }

    try:
        completed = subprocess.run(
            [sys.executable, str(path)],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "name": name,
            "passed": False,
            "reason": "TIMEOUT",
        }

    output = completed.stdout

    if expected_count is None:
        # AQ has its own aggregate regression summary.
        passed = (
            completed.returncode == 0
            and "[REGRESSION] SUITES=4/4" in output
            and "[REGRESSION] FINAL=PASS" in output
        )
    else:
        count = sum(
            line.startswith("[TEST] ")
            and line.endswith("= True")
            for line in output.splitlines()
        )

        passed = (
            completed.returncode == 0
            and count == expected_count
            and "[TEST] ALL PASS:" in output
        )

    return {
        "name": name,
        "passed": passed,
        "reason": (
            "PASS"
            if passed
            else f"EXIT_{completed.returncode}"
        ),
    }


def main():
    results = [
        run_suite(name, filename, expected)
        for name, filename, expected in TEST_FILES
    ]

    print("===== LLM REGRESSION SUMMARY =====")

    for result in results:
        status = (
            "PASS" if result["passed"] else "FAIL"
        )

        print(
            f"[REGRESSION] {result['name']}="
            f"{status} REASON={result['reason']}"
        )

    passed = sum(r["passed"] for r in results)

    print(
        f"[REGRESSION] SUITES="
        f"{passed}/{len(results)}"
    )

    if passed != len(results):
        print("[REGRESSION] FINAL=FAIL")
        return 1

    print("[REGRESSION] FINAL=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
