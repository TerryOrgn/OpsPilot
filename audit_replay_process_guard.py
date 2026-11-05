
import sqlite3
import uuid
from datetime import datetime, timezone


class ReplayProcessGuard:
    def __init__(self, db_path):
        self._db_path = str(db_path)

        with sqlite3.connect(self._db_path, timeout=5) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS REPLAY_ACTIVE_LOCK (
                    EVENT_ID TEXT PRIMARY KEY,
                    OWNER_TOKEN TEXT NOT NULL,
                    ACQUIRED_AT TEXT,
                    REPLAY_ATTEMPT_ID TEXT
                )
            """)

            # Migrate existing BO-8K databases.
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(REPLAY_ACTIVE_LOCK)"
                )
            }

            # Add replay attempt correlation without changing existing locks.
            if "REPLAY_ATTEMPT_ID" not in columns:
                conn.execute("""
                             ALTER TABLE REPLAY_ACTIVE_LOCK
                                 ADD COLUMN REPLAY_ATTEMPT_ID TEXT
                             """)

            if "ACQUIRED_AT" not in columns:
                conn.execute("""
                    ALTER TABLE REPLAY_ACTIVE_LOCK
                    ADD COLUMN ACQUIRED_AT TEXT
                """)

    def try_acquire(self, event_id,replay_attempt_id=None):
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id is required")

        if replay_attempt_id is not None:
            if (
                    not isinstance(replay_attempt_id, str)
                    or not replay_attempt_id.strip()
            ):
                raise ValueError("replay_attempt_id must be non-empty")

        token = uuid.uuid4().hex
        acquired_at = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self._db_path, timeout=5) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO REPLAY_ACTIVE_LOCK
                        (EVENT_ID, OWNER_TOKEN, ACQUIRED_AT, REPLAY_ATTEMPT_ID)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_id, token, acquired_at,replay_attempt_id),
                )
            except sqlite3.IntegrityError:
                return None

        return token

    def release(self, event_id, owner_token):
        if not owner_token:
            raise ValueError("owner_token is required")

        with sqlite3.connect(self._db_path, timeout=5) as conn:
            cursor = conn.execute(
                """
                DELETE FROM REPLAY_ACTIVE_LOCK
                WHERE EVENT_ID = ?
                  AND OWNER_TOKEN = ?
                """,
                (event_id, owner_token),
            )

        return cursor.rowcount == 1
