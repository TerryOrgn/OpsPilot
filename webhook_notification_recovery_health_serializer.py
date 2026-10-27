
from datetime import datetime, timezone


SCHEMA_VERSION = "1.0"
SUPPORTED_VERSIONS = frozenset({"1.0"})

class WebhookNotificationRecoveryHealthSerializer:
    SCHEMA_VERSION = "1.0"
    SUPPORTED_VERSIONS = frozenset({"1.0"})

    HEALTH_STATUSES = {
        "HEALTHY",
        "DEGRADED",
        "UNHEALTHY",
    }

    RECOVERY_STATUSES = {
        "NOT_RUN",
        "DISABLED",
        "DRY_RUN",
        "EXECUTED",
        "FAILED",
    }

    READINESS_REASONS = {
        "READY",
        "GUARD_DISABLED",
        "DRY_RUN_ENABLED",
        "SCHEDULER_UNHEALTHY",
    }

    REQUIRED_FIELDS = {
        "scheduler_health",
        "health_reason",
        "recovery_status",
        "ready_for_recovery",
        "readiness_reason",
        "total_runs",
        "consecutive_failures",
        "last_success_time",
    }

    def serialize(self, snapshot, schema_version="1.0"):
        if (
                type(schema_version) is not str
                or schema_version not in self.SUPPORTED_VERSIONS
        ):
            raise ValueError(
                f"Unsupported schema version: {schema_version}"
            )
        if not isinstance(snapshot, dict):
            raise TypeError("Snapshot must be a dictionary")

        if set(snapshot.keys()) != self.REQUIRED_FIELDS:
            raise ValueError("Invalid snapshot fields")

        health = snapshot["scheduler_health"]
        recovery = snapshot["recovery_status"]
        readiness = snapshot["readiness_reason"]
        ready = snapshot["ready_for_recovery"]

        if health not in self.HEALTH_STATUSES:
            raise ValueError("Invalid scheduler health")

        if recovery not in self.RECOVERY_STATUSES:
            raise ValueError("Invalid recovery status")

        if readiness not in self.READINESS_REASONS:
            raise ValueError("Invalid readiness reason")

        if type(ready) is not bool:
            raise ValueError("ready_for_recovery must be bool")

        expected_ready = (
            readiness == "READY"
        )

        if ready != expected_ready:
            raise ValueError("Inconsistent readiness")

        if readiness == "READY":
            if health == "UNHEALTHY":
                raise ValueError("Unhealthy cannot be ready")
            if recovery in {"DISABLED", "DRY_RUN"}:
                raise ValueError(
                    "Non-executing mode cannot be ready"
                )

        for name in (
            "total_runs",
            "consecutive_failures",
        ):
            value = snapshot[name]

            if type(value) is not int or value < 0:
                raise ValueError(
                    f"{name} must be non-negative integer"
                )

        if (
            snapshot["consecutive_failures"]
            > snapshot["total_runs"]
        ):
            raise ValueError(
                "Failures cannot exceed total runs"
            )

        reason = snapshot["health_reason"]

        if not isinstance(reason, str) or not reason:
            raise ValueError("Invalid health reason")

        last_success = snapshot["last_success_time"]

        if last_success is None:
            timestamp = None

        elif isinstance(last_success, datetime):
            if last_success.tzinfo is None:
                # Existing Scheduler timestamps are naive
                # local datetimes. Do not pretend they are UTC.
                timestamp = last_success.isoformat(
                    timespec="microseconds"
                )
            else:
                timestamp = last_success.astimezone(
                    timezone.utc
                ).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")

        else:
            raise ValueError(
                "last_success_time must be datetime or None"
            )

        return {
            "schema_version": schema_version,
            "scheduler_health": health,
            "health_reason": reason,
            "recovery_status": recovery,
            "ready_for_recovery": ready,
            "readiness_reason": readiness,
            "total_runs": snapshot["total_runs"],
            "consecutive_failures": snapshot[
                "consecutive_failures"
            ],
            "last_success_time": timestamp,
        }
