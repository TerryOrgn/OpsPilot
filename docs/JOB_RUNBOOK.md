# JOB v1 部署与运行手册

## 环境

本次验证环境：项目现有 `.venv`，Python 3.14、MySQL 8 语法（SKIP LOCKED）、APScheduler 3。依赖见 `requirements-job.txt`。使用现有已初始化 schema；本交付不执行生产 DDL、数据迁移或生产启动。

复制 `.env.example` 为本机私有配置，填写凭证，权限设为仅本人可读。不要提交 `.env`。启动前显式设置 MYSQL_DATABASE 与 OPSPILOT_EXPECTED_DATABASE 为同一个经批准的目标库。测试只能为 opspilot_test。正常运行需要现有 JOB_MONITOR checkpoint；禁止以删除/重建 checkpoint 方式处理故障。

```sh
MYSQL_DATABASE=opspilot_test OPSPILOT_EXPECTED_DATABASE=opspilot_test .venv/bin/python scheduler.py
```

该命令是持续服务，会处理目标库现存记录；验收只运行 README 中的 acceptance 入口。

## 上线前只读检查

由运维在目标环境注入数据库配置后，先运行：

```sh
.venv/bin/python job_preflight.py
```

检查要求显式指定且匹配的目标库，验证 JOB 表的关键列和现有 JOB_MONITOR 水位。调度器从命令行启动时也会执行此检查。它只验证读取能力。写权限、表约束及生产配置仍需由运维按部署清单核对。失败时请通过受限渠道检查数据库配置和 schema，避免输出凭证。

## 配置

| 环境变量 | 默认 | 合法范围 |
|---|---:|---|
| OPSPILOT_MONITOR_SECONDS | 60 | 1–86400 |
| OPSPILOT_NOTIFICATION_SECONDS | 60 | 1–86400 |
| OPSPILOT_NOTIFICATION_BATCH | 10 | 1–1000 |
| OPSPILOT_PROCESSING_TIMEOUT_SECONDS | 300 | 1–86400 |
| OPSPILOT_RETRY_SECONDS | 60 | 1–86400 |
| OPSPILOT_LOG_LEVEL | INFO | DEBUG/INFO/WARNING/ERROR/CRITICAL |

失败重试按 UPDATED_AT 延迟，批次先选定 ID，同一轮不会反复消费同一个失败任务。超时回收使用数据库时钟，并清除旧 token。回收覆盖该类型所有超时记录，发送批次有上限。timeout 应大于最慢正常发送时长；并发 Worker 场景可能出现超时后的重复投递。

## 运行保护

每个调度任务 max_instances=1、coalesce=True、misfire_grace_time=30。监控沿用 MySQL 命名锁，连接错误不能视作获取成功，释放异常不覆盖原业务异常。命名锁连接与业务连接分离：锁连接中断时不保证正在进行的业务立即停止；v1 建议单服务实例，告警唯一约束仍需保留。不要将 APScheduler 的进程内限制当成跨主机锁。

SIGTERM 和 Ctrl+C 等待正在执行的任务结束。先停止服务，再更新代码，再运行隔离验收，通过后由运维启动。不要 kill -9；若确需强制停止，下次通知周期会回收超时 PROCESSING。

## 最小权限

服务账号只需指定目标库：JOB_EXECUTION_LOG SELECT；JOB_MONITOR_CHECKPOINT SELECT/UPDATE；JOB_ALERT_HISTORY SELECT/INSERT/UPDATE；JOB_ALERT_STATUS_HISTORY SELECT/INSERT；JOB_NOTIFICATION_HISTORY SELECT/INSERT/UPDATE。不授予 DROP、ALTER、CREATE、全局管理或生产跨库权限。测试账号仅限 opspilot_test，并为以上表添加 INSERT/DELETE 权限以创建/清理 UUID fixture。建表/迁移由独立维护账号执行；本次未修改数据库账号或授权。

## 可观测性与故障处理

日志输出 stdout/stderr，由 launchd 或现有进程管理器采集并轮转。通知批次记录 recovered/sent/failed/skipped 和按状态分组积压；每个通知错误只记录 ID 与错误类型。服务日志 formatter 对环境中的 PASSWORD/SECRET/TOKEN/API_KEY 值脱敏。业务原始消息及数据库 LAST_ERROR_MESSAGE 可能含输入内容，应限制日志/数据库读取权限，不粘贴凭证到问题报告。

- FAILED：检查错误类型和配置，等待重试间隔；不要手动反复启动 Worker。
- PROCESSING：先确认原 Worker 已停止，等待 timeout；不要复用旧 token。
- EXHAUSTED：人工核查原因，修复后制定受审计的单记录重放；v1 不自动无限重试。
- DB 不匹配：修正环境配置，禁止关闭测试库检查。
- 锁占用：检查是否有重复服务，停止重复实例；不要自动 KILL 其他会话。
- checkpoint 不推进：查看监控失败原因，修复后重跑；禁止回退默认水位。

## 密钥与发布

已有 Git 历史曾包含 `.env`，仅加 ignore 不会移除历史密钥。若密钥仍有效，由持有人撤销/轮换；历史清理需另行协调所有协作者后执行。此次不重写 Git 历史、不绕过 GitHub 密钥保护、不推送代码。

## 验收覆盖与限制

run_job_acceptance.py：运行配置、日志脱敏、SIGTERM、双任务注册、批次失败隔离、数据库目标保护，以及 9、10C–10F、12A。12A 是真实 MySQL monitor→告警→通知→恢复，扫描输入限定本次 JOB，不启动持续生产调度。没有执行企业生产上线、远端部署或邮件/Webhook 验收。
