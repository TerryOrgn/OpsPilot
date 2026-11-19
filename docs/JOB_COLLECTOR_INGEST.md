# JOB 日志采集器接入 API

本说明对应 `codex/collector-ingest-api` 分支的试点实现。它只支持一个 `SYSTEM_ID` 绑定到一个环境，供单源试点使用；当前看板和数据库模型尚未提供多租户隔离，不要用它承载多个互不信任的客户。

## 链路

1. 内网采集器读取 JSONL，要求每个执行都有 `started` 和 `finished` 两类事件。
2. `POST /api/collector/v1/events` 以独立 Bearer 凭证认证，写入 `JOB_EXECUTION_LOG` 和 `JOB_COLLECTOR_EVENT_RECEIPT`。
3. 事件回执和执行记录在同一事务提交；重复事件安全返回 duplicate，事件 ID 内容冲突或执行状态冲突会逐项拒收。
4. 如 `OPSPILOT_INGEST_TRIGGER_MONITOR=1` 且 Cron 功能启用，入口会在 Production 执行现有完整 monitor/notification cycle；Preview 走既有固定 fixture checkpoint 限定。锁被占用或触发失败时，事件仍已持久化，`monitoring` 返回 `deferred`/`skipped`，后续 Cron 可恢复处理。

接口契约与采集器仓库一致：请求体为 `{"schema_version":1,"events":[...]}`，响应包括 `accepted_event_ids`、`duplicate_event_ids`、`rejected` 和 `monitoring`。单批最多 100 个事件、请求体最多 1 MiB。仅接受 HTTPS 部署；服务端要求数据库时区值统一按 UTC 处理。

## 数据库迁移和最小权限

先在目标 schema 用迁移账号运行 [`migrations/002_job_collector_ingest.sql`](../migrations/002_job_collector_ingest.sql)。接收服务账号只需要：

```sql
GRANT SELECT, INSERT, UPDATE ON opspilot.JOB_EXECUTION_LOG TO 'opspilot_prod_ingest_v1'@'%';
GRANT SELECT, INSERT ON opspilot.JOB_COLLECTOR_EVENT_RECEIPT TO 'opspilot_prod_ingest_v1'@'%';
```

Preview 使用独立测试账号，并将 schema 改为 `opspilot_test`。不要给接收账号 `CREATE`、`ALTER`、`DELETE`、告警表或通知表权限。迁移和账号由数据库维护账号执行。

当前主键 `JOB_EXECUTION_LOG.EXECUTION_ID` 在 schema 内全局唯一，因此这个单源版本要求执行号在该 OpsPilot 数据库内唯一。接口从环境变量绑定唯一 `OPSPILOT_INGEST_SYSTEM_ID`，拒绝其他系统 ID。

## Vercel 环境变量

以下变量只用于该接入功能；现有 Cron 仍使用既有 `MYSQL_*` 凭证。`INGEST_*` 数据库配置必须连接到和 Cron 相同的 schema，但使用独立最小权限账号。

| 变量 | Preview | Production |
|---|---|---|
| `OPSPILOT_INGEST_ENABLED` | 验收时设为 `1`，平时 `0` | 通过 Preview 验收后再设 `1` |
| `OPSPILOT_INGEST_TOKEN` | 独立随机密钥，至少 32 字符 | 另一份独立随机密钥，至少 32 字符 |
| `OPSPILOT_INGEST_SYSTEM_ID` | `PREVIEW_TEST` | 试点系统的固定标识 |
| `OPSPILOT_INGEST_TRIGGER_MONITOR` | 可设 `1`，仅处理 `OPSPILOT_PREVIEW_EXECUTION_ID` 指定 fixture | 验收后设 `1` 可及时执行现有处理链路 |
| `INGEST_MYSQL_HOST`、`INGEST_MYSQL_PORT` | Aiven 测试库 | Aiven Production 库 |
| `INGEST_MYSQL_USER`、`INGEST_MYSQL_PASSWORD` | 专用 Preview 接收账号 | 专用 Production 接收账号 |
| `INGEST_MYSQL_DATABASE`、`INGEST_OPSPILOT_EXPECTED_DATABASE` | 都是 `opspilot_test` | 都是 Production schema，且不是 `opspilot_test` |
| `INGEST_OPSPILOT_MYSQL_TLS` | `1` | `1` |
| `INGEST_OPSPILOT_MYSQL_CA_PEM` | 需要自定义 CA 时配置 | 需要自定义 CA 时配置 |

Production 和 Preview 还需要保留现有 Cron 环境变量。接入 API 会校验 `INGEST_MYSQL_DATABASE` 与 `MYSQL_DATABASE` 完全相同、两边 expected database 匹配且 TLS 开启；任何一项不符都会拒绝连接。不要复用 `CRON_SECRET` 作为采集器 token。

## Preview 验收步骤

1. 在 `opspilot_test` 应用迁移，配置独立接收账号和上表 Preview 变量。保持 Production 接入开关关闭。
2. 准备一个 `PREVIEW_<20位小写十六进制>` 执行号，并在 Preview 环境把同一 ID 配到 `OPSPILOT_PREVIEW_EXECUTION_ID`。为它建立一个独立 checkpoint；`JOB_MONITOR` 默认水位不动。
3. 向 `/api/collector/v1/events` 发送一对 started/finished 的失败事件。认证成功时应返回事件回执；再次发送相同事件应返回 duplicate，不增加执行记录。
4. Preview 的触发器只会调用固定 fixture 的 Cron 扫描，确认该执行记录出现失败告警和通知状态。然后发送该执行的成功完成事件，再调用同一 fixture cycle 验证告警恢复。
5. 验收完成后关闭 Preview 的接入开关。保留测试回执用于验证，或按测试数据清理流程删除整套 fixture。

## 当前限制

- 只有单个系统标识/token 配置；不是多客户认证或租户隔离实现。
- 回执目前没有自动清理策略，生产启用前需确定保留期与清理流程。
- 接口确认接收后，通知是现有 `CONSOLE` 通道；企业邮件/IM 路由仍需独立配置。
- 当执行号在不同系统间重复时会冲突；多系统版本需要在数据模型中保留源执行号并生成全局内部 ID，不能靠截断拼接解决。
- 变更尚未部署；Production 开关必须保持关闭，直到 Preview 验收、权限检查与 Vercel 配置完成。
