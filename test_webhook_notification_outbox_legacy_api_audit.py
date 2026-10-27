
import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent

LEGACY_METHODS = {
    "mark_sent",
    "mark_failed",
}

EXCLUDED_DIRS = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".idea",
}

audit_filename = Path(__file__).name

production_calls = []
test_calls = []
parse_errors = []


def inspect_file(path):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))

    except (SyntaxError, UnicodeError, OSError) as error:
        parse_errors.append(
            (path.name, str(error))
        )
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        function = node.func

        if not isinstance(function, ast.Attribute):
            continue

        if function.attr not in LEGACY_METHODS:
            continue

        relative_path = path.relative_to(PROJECT_ROOT)

        record = {
            "file": str(relative_path),
            "line": node.lineno,
            "method": function.attr,
        }

        if path.name.startswith("test_"):
            test_calls.append(record)
        else:
            production_calls.append(record)


for path in PROJECT_ROOT.rglob("*.py"):
    relative_parts = path.relative_to(
        PROJECT_ROOT
    ).parts

    if any(
        part in EXCLUDED_DIRS
        for part in relative_parts
    ):
        continue

    if path.name == audit_filename:
        continue

    inspect_file(path)


print("\n========== LEGACY API AUDIT ==========")

print("\n[PRODUCTION CALLS]")

for item in production_calls:
    print(
        f"{item['file']}:{item['line']} "
        f"{item['method']}()"
    )

if not production_calls:
    print("NONE")


print("\n[TEST CALLS]")

for item in test_calls:
    print(
        f"{item['file']}:{item['line']} "
        f"{item['method']}()"
    )

if not test_calls:
    print("NONE")


print("\n[PARSE ERRORS]")

for filename, error in parse_errors:
    print(f"{filename}: {error}")

if not parse_errors:
    print("NONE")


print("\n========== SUMMARY ==========")

print(
    "[AUDIT] PRODUCTION_CALL_COUNT=",
    len(production_calls),
)

print(
    "[AUDIT] TEST_CALL_COUNT=",
    len(test_calls),
)

print(
    "[AUDIT] PARSE_ERROR_COUNT=",
    len(parse_errors),
)

if parse_errors:
    print(
        "[AUDIT] RESULT= INCOMPLETE_PARSE_ERRORS"
    )
elif production_calls:
    print(
        "[AUDIT] RESULT= MIGRATION_REQUIRED"
    )
else:
    print(
        "[AUDIT] RESULT= NO_PRODUCTION_CALLS_FOUND"
    )
