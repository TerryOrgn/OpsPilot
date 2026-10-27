
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

TEST_FILES = [
    (
        "AM_TOOL_DEFINITION",
        "test_webhook_notification_recovery_tool_definition.py",
        12,
    ),
    (
        "AN_TOOL_DISPATCHER",
        "test_webhook_notification_recovery_tool_dispatcher.py",
        14,
    ),
    (
        "AO_AGENT_LOOP",
        "test_webhook_notification_recovery_agent_loop.py",
        15,
    ),
    (
        "AP_AGENT_DECISION",
        "test_webhook_notification_recovery_agent_decision.py",
        14,
    ),
]


def run_test(name, filename, expected_count):
    path = BASE_DIR / filename

    if not path.is_file():
        return {
            "name": name,
            "passed": False,
            "count": 0,
            "reason": "TEST_FILE_MISSING",
        }

    result = subprocess.run(
        [sys.executable, str(path)],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    output = result.stdout + "\n" + result.stderr

    print(f"\n===== {name} =====")
    print(output.strip())

    pass_count = sum(
        line.startswith("[TEST] ")
        and line.endswith("= True")
        for line in result.stdout.splitlines()
    )

    all_pass_marker = (
        "[TEST] ALL PASS:" in result.stdout
    )

    passed = (
        result.returncode == 0
        and pass_count == expected_count
        and all_pass_marker
    )

    return {
        "name": name,
        "passed": passed,
        "count": pass_count,
        "reason": (
            "PASS" if passed
            else f"EXIT_CODE_{result.returncode}"
        ),
    }


def main():
    results = []

    for name, filename, expected in TEST_FILES:
        try:
            result = run_test(
                name,
                filename,
                expected,
            )
        except subprocess.TimeoutExpired:
            result = {
                "name": name,
                "passed": False,
                "count": 0,
                "reason": "TIMEOUT",
            }

        results.append(result)

    print("\n===== REGRESSION SUMMARY =====")

    for result in results:
        status = (
            "PASS" if result["passed"]
            else "FAIL"
        )

        print(
            f"[REGRESSION] {result['name']}="
            f"{status} "
            f"COUNT={result['count']} "
            f"REASON={result['reason']}"
        )

    total = len(results)
    passed_count = sum(
        result["passed"] for result in results
    )

    print(
        f"[REGRESSION] SUITES="
        f"{passed_count}/{total}"
    )

    if passed_count != total:
        print("[REGRESSION] FINAL=FAIL")
        return 1

    print("[REGRESSION] FINAL=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
