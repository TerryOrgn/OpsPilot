
class ReplayLockReview:
    TERMINAL_STATUSES = {"SUCCESS", "FAILED"}

    def build(self, locks, audit_records):
        reports = []

        for lock in locks:
            event_id = lock["event_id"]

            matching = [
                record
                for record in audit_records
                if record.get("event_id") == event_id
            ]

            statuses = [
                record.get("status")
                for record in matching
            ]

            last_status = statuses[-1] if statuses else None

            terminal_found = any(
                status in self.TERMINAL_STATUSES
                for status in statuses
            )

            reports.append({
                "event_id": event_id,
                "lock_status": lock["status"],
                "last_audit_status": last_status,
                "terminal_audit_found": terminal_found,
                "recommendation": "MANUAL_REVIEW_REQUIRED",
            })

        return reports
