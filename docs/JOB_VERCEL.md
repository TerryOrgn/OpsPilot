# JOB 监控的 Vercel 部署

通过受保护的 `GET /api/job-cron` 手动触发。正式部署注册每日一次的巡检。Python Function 执行一轮监控及 CONSOLE 通知，复用原有的 checkpoint、命名锁和通知事务。现有的本地验收 UI 继续在 Mac 上运行。Vercel 项目只部署后台入口。

## 部署前

- Hobby 适用于个人非商业用途，原生 Cron 最短每天一次。当前按个人演示配置。需要每分钟自动监控时，先确定符合用途的计划，再配置分钟级 Cron。
- 选择 Vercel Function 能通过网络及 TLS 访问的 MySQL 8 端点。Mac 上的 `127.0.0.1` 仅供本地开发。
- 按 [运行手册](JOB_RUNBOOK.md) 准备最小权限账号、表结构与现有 `JOB_MONITOR` 水位。只读预检会拒绝缺失水位的环境。
- 处理 Git 历史中出现过的密钥，确认待部署源码的范围。Vercel 中通过环境变量配置凭证。

## 环境变量

| 变量 | 用途 |
|---|---|
| `CRON_SECRET` | Vercel Cron Bearer 凭证，使用独立随机值 |
| `OPSPILOT_CRON_ENABLED` | 默认禁用。完成对应环境验收后设置为 `1` |
| `MYSQL_HOST`、`MYSQL_PORT` | 可从目标环境访问的 MySQL 地址 |
| `MYSQL_USER`、`MYSQL_PASSWORD` | 对应环境专用账号 |
| `MYSQL_DATABASE`、`OPSPILOT_EXPECTED_DATABASE` | 两者必须完全一致，Preview 只允许 `opspilot_test` |
| `OPSPILOT_MYSQL_TLS` | Production 要求 `1`，使用受信任证书并校验主机名 |

## 验收与上线

1. 建立 Preview，先保持执行禁用。此阶段无需配置数据库，可核对入口与鉴权。按下文准备独立 fixture，再仅对该 Preview 分支启用手工调用。
2. 验证未授权请求返回 401，禁用或隔离配置缺失时返回 503。启用后验证只扫描指定测试 JOB、只处理该 JOB 的通知并推进独立 checkpoint。检查重叠请求跳过，确认代表性扫描在 60 秒限制内。
3. 正式部署使用 `0 1 * * *`，即每天北京时间 09:00 所在的小时。Hobby 在该小时内触发。核对正式数据库连通性、TLS、最小权限和初始 JOB_MONITOR 水位后，再启用 Production 执行开关。
4. 如需停用，先在 Vercel 控制台关闭 Cron，或更新禁用开关并重新部署。回滚部署时另行核对活跃的 Cron 配置。保留当前数据库水位。

Vercel 原生 Cron 在失败后不会补跑同一次请求。下次触发由应用按已有水位和通知状态继续处理。CONSOLE 输出在函数日志中。

## 只读看板与执行器

首页 `/` 提供密码保护的只读看板。Production 设置 `OPSPILOT_DASHBOARD_PASSWORD`，浏览器登录用户名为 `opspilot`。配置更新后重新部署。看板账号仅需三张表的 SELECT 权限，分别是 JOB_EXECUTION_LOG、JOB_ALERT_HISTORY、JOB_NOTIFICATION_HISTORY。

现有演示部署可继续使用 MYSQL_*。同时部署生产执行器时，为看板使用完整的独立配置：DASHBOARD_MYSQL_HOST、DASHBOARD_MYSQL_PORT、DASHBOARD_MYSQL_USER、DASHBOARD_MYSQL_PASSWORD、DASHBOARD_MYSQL_DATABASE、DASHBOARD_OPSPILOT_EXPECTED_DATABASE、DASHBOARD_OPSPILOT_MYSQL_TLS。看板的两个库名都填 opspilot_test，TLS 填 1。自定义 CA 填 DASHBOARD_OPSPILOT_MYSQL_CA_PEM，沿用旧配置时填 OPSPILOT_MYSQL_CA_PEM。执行器继续使用自己的 MYSQL_* 和 OPSPILOT_*。上线前先分别验证看板读取和执行器的隔离验收。

## Preview 后台隔离验收

在 Aiven 的测试库连接中先执行 `SELECT DATABASE()`。只有结果为 `opspilot_test` 时才继续。在同一会话准备一次性 JOB 和同名 checkpoint：

```sql
SET @fixture = CONCAT('PREVIEW_', LEFT(REPLACE(UUID(), '-', ''), 20));
START TRANSACTION;
INSERT INTO JOB_EXECUTION_LOG
    (EXECUTION_ID, SYSTEM_ID, JOB_NAME, BUSINESS_DATE, START_TIME, END_TIME, STATUS, ERROR_MESSAGE)
VALUES
    (@fixture, 'PREVIEW_TEST', 'Preview 验收任务', CURRENT_DATE(), NOW(3), NOW(3), 'FAILED', 'Preview fixture');
INSERT INTO JOB_MONITOR_CHECKPOINT (MONITOR_NAME, LAST_SCAN_TIME, SCAN_STATUS)
VALUES (@fixture, NOW(3), 'SUCCESS');
COMMIT;
SELECT @fixture AS preview_execution_id;
```

在 Vercel 将以下设置限定到用于验收的 Preview 分支：

- MYSQL_HOST、MYSQL_PORT、MYSQL_USER、MYSQL_PASSWORD 使用 Aiven 测试库执行账号。权限参考运行手册，线上看板账号只用于查询。
- MYSQL_DATABASE 和 OPSPILOT_EXPECTED_DATABASE 均为 opspilot_test，OPSPILOT_MYSQL_TLS 为 1。需要自定义 CA 时填 OPSPILOT_MYSQL_CA_PEM。
- OPSPILOT_PREVIEW_EXECUTION_ID 填写查询返回的 ID。配置独立的 CRON_SECRET。确认 fixture 已创建后，将 OPSPILOT_CRON_ENABLED 设为 1 并重新部署该 Preview。

通过带 Bearer 凭据的 GET 调用 Preview 的 /api/job-cron。若 Preview 还启用了 Vercel 部署保护，先通过项目授权的方式访问部署。日志和响应只用于验收当前 fixture。每次最多处理该 JOB 的 10 条到期 CONSOLE 通知，进程锁竞争时返回 skipped。

检查本次 JOB 的失败告警及通知，然后在同一测试库将这条 fixture 标记为 SUCCESS，再调用一轮验证告警恢复和恢复通知。重试和超时回收用同一 fixture 的通知记录另行构造，避免修改共享队列。验收前后核对默认 JOB_MONITOR 水位和现有历史记录。验收后将该 Preview 的启用开关设为 0 并重新部署。
