
from datetime import date, datetime


class MySQLJobRepository:

    STATUSES = ("FAILED", "TIMEOUT", "RUNNING")

    SQL = """
        SELECT
            EXECUTION_ID,
            JOB_NAME,
            STATUS,
            UPDATED_AT
        FROM JOB_EXECUTION_LOG
        WHERE STATUS IN ('FAILED', 'TIMEOUT', 'RUNNING')
        ORDER BY UPDATED_AT DESC, EXECUTION_ID DESC
        LIMIT %s
    """

    SQL_BY_STATUS = """
        SELECT
            EXECUTION_ID,
            JOB_NAME,
            STATUS,
            UPDATED_AT
        FROM JOB_EXECUTION_LOG
        WHERE STATUS = %s
        ORDER BY UPDATED_AT DESC, EXECUTION_ID DESC
        LIMIT %s
    """

    def __init__(
        self,
        connection_factory,
        fetch_limit=100,
        partition_by_status=False,
    ):
        if not callable(connection_factory):
            raise ValueError(
                "connection_factory must be callable"
            )

        if (
            isinstance(fetch_limit, bool)
            or not isinstance(fetch_limit, int)
            or not 1 <= fetch_limit <= 100
        ):
            raise ValueError(
                "fetch_limit must be between 1 and 100"
            )

        if not isinstance(partition_by_status, bool):
            raise ValueError(
                "partition_by_status must be a boolean"
            )

        self._connection_factory = connection_factory
        self._fetch_limit = fetch_limit
        self._partition_by_status = partition_by_status

    @staticmethod
    def _map_rows(rows):
        jobs = []

        for row in rows:
            execution_id, job_name, status, updated_at = row

            if isinstance(updated_at, (datetime, date)):
                updated_at = updated_at.isoformat()

            jobs.append({
                "execution_id": execution_id,
                "job_name": job_name,
                "status": status,
                "updated_at": updated_at,
            })

        return jobs

    def get_recent_jobs(self):
        connection = None
        cursor = None

        try:
            connection = self._connection_factory()
            cursor = connection.cursor()

            if self._partition_by_status:
                rows = []

                for status in self.STATUSES:
                    cursor.execute(
                        self.SQL_BY_STATUS,
                        (status, self._fetch_limit),
                    )
                    rows.extend(cursor.fetchall())

                jobs = self._map_rows(rows)

                jobs.sort(
                    key=lambda job: (
                        job["updated_at"],
                        job["execution_id"],
                    ),
                    reverse=True,
                )

                return jobs

            cursor.execute(
                self.SQL,
                (self._fetch_limit,),
            )

            return self._map_rows(cursor.fetchall())

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None:
                connection.close()
