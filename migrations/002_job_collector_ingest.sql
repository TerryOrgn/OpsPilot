-- Apply with a dedicated migration account in the selected OpsPilot schema.
-- The ingest service account needs SELECT/INSERT on this table and
-- SELECT/INSERT/UPDATE on JOB_EXECUTION_LOG; it does not need alert/outbox rights.
CREATE TABLE `JOB_COLLECTOR_EVENT_RECEIPT` (
  `SYSTEM_ID` varchar(50) NOT NULL,
  `EVENT_ID` varchar(200) NOT NULL,
  `EXECUTION_ID` varchar(64) NOT NULL,
  `EVENT_TYPE` varchar(20) NOT NULL,
  `PAYLOAD_SHA256` char(64) NOT NULL,
  `RECEIVED_AT` datetime(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`SYSTEM_ID`, `EVENT_ID`),
  KEY `IDX_COLLECTOR_RECEIPT_EXECUTION` (`SYSTEM_ID`, `EXECUTION_ID`),
  CONSTRAINT `job_collector_receipt_chk_1`
    CHECK (`EVENT_TYPE` in (_utf8mb4'started', _utf8mb4'finished'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Idempotency receipts for customer-side JOB collectors';
