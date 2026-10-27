
import json

from mysql.connector import IntegrityError


class MySQLAuditSink:
    INSERT_SQL = """
        INSERT INTO AGENT_AUDIT_LOG (
            EVENT_ID,
            REQUEST_ID,
            EVENT,
            TOOL_NAME,
            TOTAL_ABNORMAL_COUNT,
            RETURNED_COUNT,
            TRUNCATED,
            SUMMARY_STATUS
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    def __init__(self, connection_factory):
        if not callable(connection_factory):
            raise ValueError(
                "connection_factory must be callable"
            )
        self._connection_factory = connection_factory

    def write(self, payload):
        audit = json.loads(payload)

        params = (
            audit.get("event_id"),
            audit.get("request_id"),
            audit["event"],
            audit["tool_name"],
            audit["total_abnormal_count"],
            audit["returned_count"],
            audit["truncated"],
            audit["summary_status"],
        )

        connection = self._connection_factory()

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(self.INSERT_SQL, params)
                connection.commit()

            except IntegrityError as exc:
                connection.rollback()

                # 仅将 EVENT_ID 唯一索引冲突视为幂等重复
                if (
                    exc.errno == 1062
                    and "UK_AUDIT_EVENT_ID"
                    in str(exc)
                    and audit.get("event_id") is not None
                ):
                    return

                raise

            finally:
                cursor.close()

        except IntegrityError:
            raise

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()
