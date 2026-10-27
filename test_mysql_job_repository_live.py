
import json
import os

import mysql.connector

from mysql_job_repository import MySQLJobRepository
from job_monitoring_tool import JobMonitoringTool


def connection_factory():
    return mysql.connector.connect(
        host=os.getenv("OPSPILOT_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("OPSPILOT_DB_PORT", "3306")),
        user=os.environ["OPSPILOT_DB_USER"],
        password=os.environ["OPSPILOT_DB_PASSWORD"],
        database=os.environ["OPSPILOT_DB_NAME"],
        connection_timeout=5,
    )


def main():
    repository = MySQLJobRepository(
        connection_factory=connection_factory,
        fetch_limit=100,
    )

    candidates = repository.get_recent_jobs()

    statuses = [job["status"] for job in candidates]

    assert all(
        status in {"FAILED", "TIMEOUT", "RUNNING"}
        for status in statuses
    )

    print("[LIVE] CANDIDATE_QUERY=PASS")
    print("[LIVE] CANDIDATE_COUNT=", len(candidates))
    print("[LIVE] CANDIDATE_STATUSES=", statuses)

    tool = JobMonitoringTool(repository)

    result = tool.execute(limit=10)

    assert result["schema_version"] == "1.0"
    assert result["tool_name"] == "get_recent_abnormal_jobs"
    assert result["abnormal_count"] == len(result["jobs"])

    for job in result["jobs"]:
        assert job["status"] in {"FAILED", "TIMEOUT"}

    print("[LIVE] MYSQL_CONNECTION=PASS")
    print("[LIVE] JOB_TOOL_INTEGRATION=PASS")
    print(
        "[LIVE] ABNORMAL_COUNT=",
        result["abnormal_count"],
    )
    print(
        "[LIVE] STATUS_SUMMARY=",
        json.dumps(
            [job["status"] for job in result["jobs"]]
        ),
    )


    # BI: Enable RUNNING timeout detection.
    timeout_tool = JobMonitoringTool(
        repository=repository,
        enable_timeout_detection=True,
    )

    timeout_result = timeout_tool.execute(limit=100)
    timeout_jobs = timeout_result["jobs"]

    assert timeout_result["abnormal_count"] == len(timeout_jobs)

    assert all(
        job["status"] in {"FAILED", "TIMEOUT"}
        for job in timeout_jobs
    )

    assert all(
        job["detected_status"] == job["status"]
        for job in timeout_jobs
    )

    print("[LIVE] TIMEOUT_DETECTION=PASS")
    print(
        "[LIVE] DETECTED_ABNORMAL_COUNT=",
        timeout_result["abnormal_count"],
    )
    print(
        "[LIVE] DETECTED_STATUSES=",
        [job["status"] for job in timeout_jobs],
    )
    print(
        "[LIVE] RUNNING_TO_TIMEOUT_COUNT=",
        sum(
            job["original_status"] == "RUNNING"
            and job["detected_status"] == "TIMEOUT"
            for job in timeout_jobs
        ),
    )


    # BJ-4: Partitioned query verification.
    partitioned_repository = MySQLJobRepository(
        connection_factory=connection_factory,
        fetch_limit=100,
        partition_by_status=True,
    )

    partitioned_jobs = (
        partitioned_repository.get_recent_jobs()
    )

    statuses = [
        job["status"]
        for job in partitioned_jobs
    ]

    assert all(
        status in {"FAILED", "TIMEOUT", "RUNNING"}
        for status in statuses
    )

    assert all(
        partitioned_jobs[i]["updated_at"]
        >= partitioned_jobs[i + 1]["updated_at"]
        for i in range(len(partitioned_jobs) - 1)
    )

    print("[LIVE] PARTITIONED_QUERY=PASS")
    print(
        "[LIVE] PARTITIONED_COUNT=",
        len(partitioned_jobs),
    )
    print(
        "[LIVE] PARTITIONED_FAILED=",
        statuses.count("FAILED"),
    )
    print(
        "[LIVE] PARTITIONED_TIMEOUT=",
        statuses.count("TIMEOUT"),
    )
    print(
        "[LIVE] PARTITIONED_RUNNING=",
        statuses.count("RUNNING"),
    )




if __name__ == "__main__":
    main()
