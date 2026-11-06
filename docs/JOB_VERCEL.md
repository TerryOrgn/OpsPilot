# JOB 监控的 Vercel 部署

通过受保护的 `GET /api/job-cron` 手动触发。当前 Hobby 配置不注册自动调度。Python Function 执行一轮监控及 CONSOLE 通知，复用原有的 checkpoint、命名锁和通知事务。现有的本地验收 UI 继续在 Mac 上运行。Vercel 项目只部署后台入口。

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

1. 建立 Preview，先保持执行禁用。此阶段无需配置数据库，可核对入口与鉴权。准备云端测试库后，在 Preview 配置独立 `opspilot_test`，启用执行，再通过带 Bearer 凭证的手工 GET 验收。
2. 验证未授权请求返回 401，禁用时返回 503，启用后正确处理测试数据。检查重叠请求跳过以及日志中的耗时，确认代表性扫描在 60 秒限制内。部署前应估算积压，避免一次扫描超过函数时限。
3. 准备正式运行时，先确认计划符合用途。若选用 Pro 或 Enterprise 的分钟调度，在 vercel.json 加入 `"crons": [{"path": "/api/job-cron", "schedule": "* * * * *"}]`。Production 保持禁用，确认数据库连通性、TLS、最小权限和水位后再启用。
4. 如需停用，先在 Vercel 控制台关闭 Cron，或更新禁用开关并重新部署。回滚部署时另行核对活跃的 Cron 配置。保留当前数据库水位。

Vercel 原生 Cron 在失败后不会补跑同一次请求。下次触发由应用按已有水位和通知状态继续处理。CONSOLE 输出在函数日志中。
