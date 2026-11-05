
import sqlite3
from datetime import datetime, timezone


class ReplayLockInspector:
    def __init__(self, db_path, stale_after_seconds=1800):
        if stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")

        self._db_path = str(db_path)
        self._stale_after_seconds = stale_after_seconds

    def list_active_locks(self):
        now = datetime.now(timezone.utc)

        with sqlite3.connect(self._db_path, timeout=5) as conn:
            rows = conn.execute("""
                SELECT EVENT_ID, OWNER_TOKEN, ACQUIRED_AT, REPLAY_ATTEMPT_ID
                FROM REPLAY_ACTIVE_LOCK
                ORDER BY EVENT_ID
            """).fetchall()

        result = []

        for event_id, owner_token, acquired_at,replay_attempt_id in rows:
            status = "AGE_UNKNOWN"
            age_seconds = None

            if acquired_at is not None:
                try:
                    acquired = datetime.fromisoformat(acquired_at)

                    if acquired.tzinfo is not None:
                        age = (now - acquired).total_seconds()

                        if age >= 0:
                            age_seconds = age
                            status = (
                                "STALE_SUSPECTED"
                                if age >= self._stale_after_seconds
                                else "ACTIVE"
                            )
                except (ValueError, TypeError, OverflowError):
                    pass

            result.append({
                "event_id": event_id,
                "owner_token": owner_token,
                "acquired_at": acquired_at,
                "replay_attempt_id":replay_attempt_id,
                "age_seconds": age_seconds,
                "status": status,
            })

        return result
