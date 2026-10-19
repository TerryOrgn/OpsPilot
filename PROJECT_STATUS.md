# OpsPilot v1 — Project Status

> 项目名称：OpsPilot v1  
> 项目定位：面向企业传统 IT 运维场景的自动化监控与 AI Agent 实践项目  
> 当前阶段：Phase 7 — 告警通知管理  
> 当前步骤：Step 3 — 通知状态持久化  
> 状态更新时间：2026-10-18  
> 项目状态：本地开发与功能验证中

---

## 1. 项目目标

OpsPilot v1 是一个面向企业传统 IT 运维场景的自动化监控项目。

项目采用渐进式开发方式，从 JOB 执行监控开始，逐步扩展到告警管理、通知管理、自动化运维和 AI Agent 能力。

### 1.1 当前目标

构建一个能够自动完成以下工作的 JOB 监控系统：

1. 定期扫描 JOB 执行记录。
2. 检测执行失败、运行超时和异常数据。
3. 对重复告警进行去重。
4. 自动恢复符合条件的告警。
5. 记录完整的告警状态变化。
6. 持久化通知任务。
7. 支持通知失败重试。
8. 为后续 AI Agent 分析与自动化处置提供基础能力。

### 1.2 长期目标

逐步扩展到六类企业运维场景：

| 场景 | 目标 |
|---|---|
| JOB 监控 | 异常检测、告警、通知 |
| 证书管理 | 到期检测、更新提醒 |
| 文件处理 | 月末月初文件处理监控 |
| 漏洞治理 | 扫描结果分析、整改跟踪 |
| 基础设施维护 | 服务器与数据库升级跟踪 |
| 灾备管理 | DR 切换验证与结果分析 |

当前仅重点实现 JOB 监控，不代表其他场景已经完成。

---

## 2. 技术架构

### 2.1 技术栈

| 技术 | 用途 |
|---|---|
| Python | 核心业务逻辑 |
| MySQL 8 | 数据持久化 |
| PyMySQL | 数据库访问 |
| APScheduler 3.x | 定时任务调度 |
| python-dotenv | 环境配置 |
| logging | 日志记录 |
| PyCharm | 本地开发 |
| macOS | 本地运行环境 |

### 2.2 当前架构

```text
                APScheduler
                     |
                     v
                scheduler.py
                     |
                     v
                job_monitor.py
                     |
          +----------+----------+
          |                     |
          v                     v
        db.py              alert_manager.py
          |                     |
          v                     v
   JOB_EXECUTION_LOG     JOB_ALERT_HISTORY
          |                     |
          v                     v
 JOB_MONITOR_CHECKPOINT  JOB_ALERT_STATUS_HISTORY
                                |
                                v
                       JOB_NOTIFICATION_HISTORY
                                |
                                v
                              PENDING
```

说明：

- JOB 监控与告警持久化已经实现。
- 通知任务持久化已部分验证。
- 通知发送器尚未实现。
- AI Agent 尚未接入当前监控执行链路。

---

## 3. 项目阶段进度

| 阶段 | 主要内容 | 状态 |
|---|---|---|
| Phase 1 | JOB 数据模型 | 已完成本地验证 |
| Phase 2 | JOB 异常检测 | 已完成本地验证 |
| Phase 3 | 告警持久化与去重 | 已完成本地验证 |
| Phase 4 | 增量扫描与 Checkpoint | 已完成本地验证 |
| Phase 5 | 告警自动恢复与审计 | 已完成本地验证 |
| Phase 6 | APScheduler 调度 | 已完成本地验证 |
| Phase 7 | 告警通知管理 | 进行中 |

以上状态表示当前开发阶段的本地功能验证结果，不代表生产环境验收通过。

---

## 4. 已实现功能

### 4.1 JOB 异常检测

主要入口：

```python
detect_job_alert(job)
```

当前支持：

| 异常类型 | 检测条件 | 级别 |
|---|---|---|
| JOB_FAILED | STATUS = FAILED | CRITICAL |
| JOB_TIMEOUT | RUNNING 超过阈值 | WARNING |
| JOB_TIMEOUT | SUCCESS 但最终耗时超阈值 | WARNING |
| INVALID_EXECUTION_DATA | 时间字段异常 | WARNING |
| UNKNOWN_STATUS | 未知 JOB 状态 | WARNING |

当前超时阈值：

```python
MAX_DURATION_SECONDS = 1800
```

即 30 分钟。

### 4.2 增量扫描

核心函数：

```python
get_checkpoint()
get_incremental_jobs()
get_running_jobs()
get_job_by_execution_id()
update_checkpoint()
```

主要机制：

- 使用 `LAST_SCAN_TIME` 作为扫描水位。
- 默认使用 5 分钟重叠窗口。
- 同时查询增量 JOB 和 RUNNING JOB。
- 根据 `EXECUTION_ID` 合并去重。
- 处理前重新读取 JOB 最新状态。
- 处理成功后推进 Checkpoint。

已验证 Checkpoint 能够持续推进。

### 4.3 告警生命周期

当前支持：

```text
CREATED
   |
   v
  OPEN
   |
   +------> ACKNOWLEDGED
   |
   v
RESOLVED
   |
   v
REOPENED
   |
   v
  OPEN
```

告警事件：

| 事件 | 含义 |
|---|---|
| CREATED | 首次发现异常 |
| DUPLICATE | 重复检测已有未恢复告警 |
| REOPENED | 已恢复告警再次出现 |
| RESOLVED | 告警被恢复 |

注意：

- `CREATED`、`DUPLICATE`、`REOPENED` 已进行本地测试。
- `ACKNOWLEDGED` 状态的保持逻辑已在代码中修正，但仍建议增加专项回归测试。
- `REOPENED` 时清空历史恢复字段的功能已通过测试。

### 4.4 调度管理

主要文件：

```text
scheduler.py
```

当前配置：

```text
Interval: 60 seconds
max_instances: 1
coalesce: True
misfire_grace_time: 30
```

已验证：

- 每 60 秒执行真实 `monitor_jobs()`。
- 单进程防重入。
- 任务异常后调度器继续运行。
- 调度成功与失败统计。
- Checkpoint 持续推进。

真实监控曾连续运行 15 轮：

```text
total_runs = 15
success_count = 15
failure_count = 0
consecutive_failures = 0
```

限制：

- 调度状态目前保存在进程内存。
- 尚未验证多实例部署。
- 尚未实现独立健康检查接口。

---

## 5. 数据库设计

### 5.1 当前主要数据表

| 数据表 | 作用 |
|---|---|
| JOB_EXECUTION_LOG | JOB 执行记录 |
| JOB_MONITOR_CHECKPOINT | 增量扫描水位 |
| JOB_ALERT_HISTORY | 告警当前状态 |
| JOB_ALERT_STATUS_HISTORY | 告警状态变更审计 |
| JOB_NOTIFICATION_HISTORY | 通知任务持久化 |

### 5.2 告警唯一性

```sql
UNIQUE KEY UK_EXECUTION_ALERT (
    EXECUTION_ID,
    ALERT_TYPE
)
```

同一次 JOB 执行、同一种异常类型，最多对应一条告警主记录。

### 5.3 通知唯一性

```sql
UNIQUE KEY UK_EVENT_CHANNEL (
    EVENT_ID,
    NOTIFICATION_TYPE
)
```

同一个告警事件、同一个通知渠道，最多对应一条通知任务。

不同的 `REOPEN` 事件可以生成不同通知任务。

---

## 6. Phase 7 — 告警通知管理

### 6.1 阶段目标

实现可靠的告警通知处理机制：

```text
告警检测
    |
    v
告警状态变更
    |
    v
审计事件
    |
    v
通知任务 PENDING
    |
    v
通知发送
    |
    +----> SENT
    |
    +----> FAILED
               |
               v
             重试
```

采用 Transactional Outbox 思路：

在同一数据库事务中写入告警、审计事件和通知任务。

由独立通知发送程序处理 PENDING 任务。

### 6.2 当前步骤

| Step | 功能 | 状态 |
|---|---|---|
| Step 1 | 通知触发规则 | 已验证 |
| Step 2 | CREATED / DUPLICATE / REOPENED | 已验证 |
| Step 3 | 通知任务持久化 | 进行中 |
| Step 4 | 通知失败重试 | 未开始 |
| Step 5 | 通知集成测试 | 未开始 |

### 6.3 通知触发规则

已验证规则：

| 事件 | 是否通知 |
|---|---|
| CREATED | YES |
| DUPLICATE | NO |
| REOPENED | YES |
| RESOLVED | NO |

当前 `RESOLVED` 默认不通知。

未来可根据实际业务需求扩展恢复通知。

### 6.4 通知任务状态

```text
PENDING
   |
   +------> SENT
   |
   +------> FAILED
                |
                v
              RETRY
```

当前仅实现 PENDING 任务的创建。

尚未实现实际发送和状态更新。

---

## 7. Phase 7 已完成测试

### 7.1 REOPENED 状态恢复测试

测试对象：

```text
EXECUTION_ID = TEST-REOPEN-001
ALERT_ID = 119
```

验证结果：

```text
ALERT_STATUS = OPEN
DETECT_COUNT = 3

RESOLVED_AT = NULL
RESOLUTION_TYPE = NULL
RESOLUTION_REASON = NULL
```

审计记录：

```text
CREATE
MANUAL_RESOLVE
REOPEN
MANUAL_RESOLVE
REOPEN
```

结果：

PASS

### 7.2 DUPLICATE 不创建通知

测试对象：

```text
EXEC-007
EXEC-008
TEST-REOPEN-001
```

监控输出：

```text
[DUPLICATE] EXEC-007
[DUPLICATE] EXEC-008
[DUPLICATE] TEST-REOPEN-001
```

通知表记录数：

```text
NOTIFICATION_COUNT = 0
```

结果：

PASS

说明：

该测试验证了已有告警重复扫描时未创建通知任务。

### 7.3 CREATED 通知任务创建

测试对象：

```text
EXECUTION_ID = TEST-NOTIFY-002
```

数据库结果：

```text
ALERT_ID = 121
EVENT_ID = 13
NOTIFICATION_ID = 1

NOTIFICATION_TYPE = CONSOLE
NOTIFICATION_STATUS = PENDING
```

创建时间：

```text
2026-10-16 20:25:24.022
```

监控输出：

```text
[NEW ALERT] EXECUTION_ID=TEST-NOTIFY-002
[SUCCESS] 本轮监控完成
```

结果：

PASS

已验证新告警可以生成持久化通知任务。

---

## 8. 当前已知问题

### ISSUE-001：历史告警缺少通知任务

测试对象：

```text
EXECUTION_ID = TEST-NOTIFY-001
ALERT_ID = 120
EVENT_ID = 12
```

实际情况：

```text
JOB_ALERT_HISTORY:
    存在

JOB_ALERT_STATUS_HISTORY:
    存在

JOB_NOTIFICATION_HISTORY:
    不存在
```

后续使用 `TEST-NOTIFY-002` 成功创建通知任务。

因此当前可以确认：

- 最新代码具备创建通知任务的能力。
- `TEST-NOTIFY-001` 的通知任务确实缺失。
- 缺失原因尚未最终确认。

可能涉及运行代码版本或执行路径差异，但目前没有充分证据确定根因。

状态：

OPEN

建议：

后续增加事务回滚测试和运行版本诊断。

不要直接将历史缺失记录视为已修复。

### ISSUE-002：诊断日志未出现

之前计划增加：

```text
[OUTBOX] 准备创建通知任务
[OUTBOX] 通知任务插入成功
```

但在 `TEST-NOTIFY-002` 的控制台输出中未观察到。

与此同时，数据库已成功保存通知任务。

状态：

待核实

建议：

统一使用 `logging` 输出诊断信息，并确认运行代码版本。

### ISSUE-003：通知事务回滚尚未验证

当前 `save_alert()` 已包含：

```python
connection.commit()
connection.rollback()
```

但尚未完成故障注入测试。

需要验证通知 INSERT 失败时：

- 告警不提交。
- 审计记录不提交。
- 通知任务不提交。

状态：

NOT TESTED

---

## 9. 当前风险与技术债

| 风险 | 影响 | 优先级 |
|---|---|---|
| 通知发送器尚未实现 | PENDING 无法发送 | 高 |
| 事务回滚未验证 | 可能存在数据不一致 | 高 |
| 历史通知缺失原因未确认 | 影响可靠性判断 | 高 |
| 多实例并发未验证 | 可能发生竞争或重复处理 | 中 |
| 调度状态仅保存在内存 | 重启后统计丢失 | 中 |
| 增量扫描重叠窗口固定 | 极端情况下可能漏扫 | 中 |
| 时间与时区处理未统一验证 | 可能影响超时判断 | 中 |
| 通知发送幂等性未实现 | 可能重复发送 | 高 |
| AI Agent 尚未接入 | 暂不具备智能分析能力 | 后续阶段 |

---

## 10. 下一步开发计划

### NEXT-001：验证 REOPENED 创建新通知

优先级：P0

测试对象：

```text
EXECUTION_ID = TEST-NOTIFY-002
ALERT_ID = 121
```

步骤：

1. 调用 `resolve_alert()` 恢复测试告警。
2. 再次运行 `job_monitor.py`。
3. 验证监控输出 `REOPENED`。
4. 查询通知表。

预期：

```text
EVENT_ID = 13
CHANGE_TYPE = CREATE
NOTIFICATION_STATUS = PENDING

EVENT_ID = 新ID
CHANGE_TYPE = REOPEN
NOTIFICATION_STATUS = PENDING
```

验收标准：

- 同一 ALERT_ID 对应两条通知任务。
- 两条通知具有不同 EVENT_ID。
- 原通知任务未被覆盖。
- 两条任务状态均为 PENDING。

### NEXT-002：验证事务回滚

优先级：P0

通过受控故障注入模拟通知 INSERT 失败。

验收标准：

- 不产生部分提交。
- 程序明确记录异常。
- 告警、审计和通知数据保持一致。

### NEXT-003：实现 notification_manager.py

优先级：P1

计划实现：

```python
get_pending_notifications()
send_console_notification()
mark_notification_sent()
mark_notification_failed()
```

第一版仅使用 CONSOLE 模拟发送。

暂不接入真实邮件和 Webhook。

### NEXT-004：实现失败重试

优先级：P1

计划实现：

- 最大重试次数。
- 重试间隔。
- 失败原因记录。
- 重试成功后的状态更新。
- 避免并发重复领取任务。

### NEXT-005：通知集成测试

优先级：P1

覆盖：

```text
CREATED → PENDING → SENT

DUPLICATE → 不创建通知

REOPENED → 新 PENDING → SENT

PENDING → FAILED → 重试 → SENT
```

---

## 11. 当前验收结论

### 已具备的能力

OpsPilot v1 当前已经能够：

- 周期性执行 JOB 监控。
- 识别 JOB 失败和超时。
- 增量扫描执行记录。
- 持久化告警。
- 对重复告警去重。
- 自动恢复符合条件的超时告警。
- 记录告警生命周期。
- 在 CREATED 场景中创建持久化通知任务。

### 尚不具备的能力

- 实际通知发送。
- 通知失败自动重试。
- 生产级通知幂等保障。
- 完整的通知事务故障验证。
- 多实例协调。
- AI Agent 自主分析与处置。

### 当前总体状态

**Phase 7 / Step 3 — IN PROGRESS**

下一项任务：

**验证 REOPENED 事件创建第二条独立 PENDING 通知任务。**

---

## 12. 开发原则

1. 每次只实现一个小功能。
2. 先验证数据库一致性，再扩展业务能力。
3. 所有关键功能必须有可复现测试。
4. 不使用真实生产敏感数据。
5. 优先使用确定性规则处理告警。
6. AI Agent 只在具有明确价值的场景中逐步引入。
7. 未经验证的功能不得标记为完成。
8. 优先保证可靠性、可审计性和可恢复性。

---

## 13. 项目恢复指引

如果需要在新的开发会话中继续，可以提供本文件并说明：

> 继续 OpsPilot v1 开发。
>
> 当前处于 Phase 7 Step 3。
>
> CREATED 通知持久化已通过测试。
> DUPLICATE 不创建通知已通过测试。
> REOPENED 通知持久化尚未验证。
>
> 请从 NEXT-001 开始，每次只安排一个可执行的小任务，并提供验收标准。
> 


下面是今天（2026-10-19）OpsPilot v1 的开发记录，采用 Markdown 格式，可以直接追加到 `PROJECT_STATUS.md`。

内容依据今天实际执行的 Python 测试和 MySQL 查询结果整理，区分了**已验证功能、已实现但未验证功能、待开发事项**。

---

# OpsPilot v1 — 开发进度记录

## 2026-10-19｜Phase 7：Notification Dispatcher 可靠性增强

### 一、今日开发概述

今日重点完善 OpsPilot v1 的通知处理模块（Notification Dispatcher），主要围绕以下能力展开：

1. 通知发送失败后的自动重试。
2. 最大重试次数控制。
3. MySQL 并发安全任务领取。
4. Dispatcher 领取任务状态管理。
5. Claim Token 领取身份校验。
6. 通知状态确认机制。

**今日成果：完成通知重试、并发领取和 Claim Token 基础能力验证。**

当前系统已具备基础的通知可靠性机制，但通知领取、发送与确认尚未整合成完整工作流。

### 二、数据库结构变更

修改表：`JOB_NOTIFICATION_HISTORY`

**1. 新增字段**

| 字段 | 类型 | 用途 | 状态 |
|---|---|---|---|
| PROCESSING_STARTED_AT | DATETIME(3) NULL | 记录通知任务开始处理时间 | 已完成 |
| CLAIM_TOKEN | VARCHAR(36) NULL | 记录 Dispatcher 领取任务的唯一标识 | 已完成 |

**2. 扩展通知状态约束**

修改 `CHK_NOTIFICATION_STATUS`，允许以下状态：

```text
PENDING
PROCESSING
SENT
FAILED
```

状态含义：

| 状态 | 含义 |
|---|---|
| PENDING | 等待发送 |
| PROCESSING | 已被 Dispatcher 领取，正在处理 |
| SENT | 通知发送成功 |
| FAILED | 通知发送失败，可能等待重试 |

其中，`FAILED` 且 `RETRY_COUNT >= 3` 的通知不再自动重试。

### 三、Python 模块修改记录

#### 3.1 notification_dispatcher.py

完善失败重试机制。

核心参数：

```python
MAX_RETRY_COUNT = 3
```

实现逻辑：

- 查询 `PENDING` 和 `FAILED` 状态的通知。
- 仅处理 `RETRY_COUNT < 3` 的通知。
- 发送成功后更新状态为 `SENT`。
- 发送成功后清空 `LAST_ERROR_MESSAGE`。
- 发送失败后更新状态为 `FAILED`。
- 每次发送失败，`RETRY_COUNT` 增加 1。
- 通过 `cursor.rowcount` 检查成功状态更新的影响行数。

已验证状态转换：

```text
PENDING → SENT

PENDING → FAILED

FAILED → SENT

FAILED → FAILED

FAILED（RETRY_COUNT=3）→ 停止重试
```

#### 3.2 notification_claim.py（新增）

新增函数：

```python
claim_notifications(limit=10, notification_type="CONSOLE")
```

实现功能：

- 开启 MySQL 事务。
- 使用 `SELECT ... FOR UPDATE OF n SKIP LOCKED` 领取通知。
- 仅领取 `PENDING` 或符合重试条件的 `FAILED` 通知。
- 将领取成功的通知更新为 `PROCESSING`。
- 记录 `PROCESSING_STARTED_AT`。
- 使用 `uuid4()` 生成唯一 `CLAIM_TOKEN`。
- 将 Claim Token 保存到数据库并返回调用方。
- 领取成功后提交事务，释放数据库行锁。
- 发生异常时执行事务回滚。

数据库版本：

```text
MySQL 8.4.9
```

已验证支持 `FOR UPDATE SKIP LOCKED`。

#### 3.3 notification_confirmation.py（新增）

新增函数：

```python
confirm_notification_sent(notification_id, claim_token)
```

实现基于 Claim Token 的通知完成确认。

核心 SQL 条件：

```sql
WHERE ID = %s
  AND NOTIFICATION_STATUS = 'PROCESSING'
  AND CLAIM_TOKEN = %s
```

只有状态为 `PROCESSING` 且 Claim Token 匹配时，才允许更新为 `SENT`。

成功确认后：

```text
NOTIFICATION_STATUS = SENT
SENT_AT = 当前时间
CLAIM_TOKEN = NULL
PROCESSING_STARTED_AT = NULL
LAST_ERROR_MESSAGE = NULL
```

**当前验证状态：错误 Token 拒绝测试通过；正确 Token 确认测试尚未执行。**

### 四、今日测试记录

| 测试脚本 / 场景 | 验证内容 | 结果 |
|---|---|---|
| test_notification_retry.py | FAILED → SENT 重试成功 | PASS |
| test_notification_max_retry.py | 连续失败 3 次后停止重试 | PASS |
| test_notification_claim.py | 首次领取成功，第二次无法重复领取 | PASS |
| test_notification_concurrent.py | 两个 Dispatcher 并发领取同一条通知 | PASS |
| MySQL 双 Session 行锁测试 | SKIP LOCKED 跳过被锁定记录 | PASS |
| test_notification_claim_token.py | Claim Token 生成、持久化及防重复领取 | PASS |
| test_notification_invalid_token.py | 错误 Token 无法更新通知状态 | PASS |
| test_notification_valid_token.py | 正确 Token 确认及重复确认拒绝 | NOT RUN |

**关键测试结果**

通知 ID=4：

```text
FAILED → SENT
RETRY_COUNT = 1
LAST_ERROR_MESSAGE = NULL
SENT_AT = 2026-10-19 17:06:24.688
```

通知 ID=5：

```text
连续失败 3 次
最终状态 = FAILED
RETRY_COUNT = 3
第四次调度处理数量 = 0
```

通知 ID=6：

```text
第一次领取 = 1
第二次领取 = 0
最终状态 = PROCESSING
```

通知 ID=7：

```text
Dispatcher A = [7]
Dispatcher B = []
合计领取数量 = 1
最终状态 = PROCESSING
```

通知 ID=9：

```text
STATUS = PROCESSING
CLAIM_TOKEN = 051a42be-62bf-45e5-9003-d1bbe2ed0a78
```

错误 Token 测试：

```text
[CONFIRM] REJECTED ID=9
[TEST] PASS：错误 Token 被拒绝
```

数据库验证：

```text
STATUS = PROCESSING
CLAIM_TOKEN 保持不变
SENT_AT = NULL
```

### 五、今日遇到的问题及解决方案

**问题 1：Dispatcher 输出 SENT，但数据库仍然为 FAILED**

现象：

```text
[DISPATCHER] SENT ID=4
```

数据库状态：

```text
NOTIFICATION_STATUS = FAILED
```

处理：

- 检查 UPDATE 的 WHERE 条件。
- 确保成功更新同时支持 `PENDING` 和 `FAILED`。
- 增加 `cursor.rowcount` 检查。
- 检查事务提交位置。

最终验证：

```text
[DISPATCHER] SENT UPDATE ID=4 UPDATED_ROWS=1
```

数据库状态成功更新为 `SENT`。

注：原始异常的唯一根因未被单独确认，最终修复版本通过测试。

**问题 2：MySQL CHECK 约束拒绝 PROCESSING 状态**

异常：

```text
pymysql.err.OperationalError:
(3819, "Check constraint 'CHK_NOTIFICATION_STATUS' is violated.")
```

原因：

数据库原有 CHECK 约束未包含新状态 `PROCESSING`。

解决：

更新 `CHK_NOTIFICATION_STATUS`，增加 `PROCESSING`。

重新运行 `test_notification_claim.py` 后通过。

### 六、当前架构

```text
JOB Monitor
     |
     v
Alert Manager
     |
     v
Transactional Outbox
     |
     v
JOB_NOTIFICATION_HISTORY
     |
     | PENDING / FAILED
     v
Notification Claim
     |
     | SELECT FOR UPDATE SKIP LOCKED
     | UUID Claim Token
     v
PROCESSING
     |
     | 尚未完成工作流整合
     v
Notification Sender
     |
     v
Token-based Confirmation
     |
     v
SENT / FAILED
```

说明：目前 `notification_dispatcher.py` 的旧发送流程与新增的 `notification_claim.py`、`notification_confirmation.py` 仍是独立实现，尚未整合。

### 七、待解决的可靠性问题

| 问题 | 当前状态 |
|---|---|
| 正确 Claim Token 确认 | 待测试 |
| 旧 Token 重复确认拒绝 | 待测试 |
| 发送失败时的 Token 校验 | 待实现 |
| PROCESSING 超时恢复 | 待实现 |
| 旧 Dispatcher 超时后状态更新防护 | 待测试 |
| Claim → Send → Confirm 流程整合 | 待实现 |
| 通知发送异常与数据库异常隔离 | 待完善 |
| 重试退避间隔 | 待实现 |
| Dispatcher 自动调度 | 待实现 |
| 外部通知接口幂等性 | 待设计 |

特别注意：

**Claim Token 可以限制旧 Dispatcher 修改数据库状态，但无法阻止已经发生的外部通知发送。**

因此，当前设计尚不能保证通知严格只发送一次。

### 八、下一次开发计划

**下一任务：验证正确 Claim Token 的状态确认。**

测试文件：

```text
test_notification_valid_token.py
```

测试对象：

```text
NOTIFICATION_ID = 9
```

验收标准：

1. 正确 Token 可以完成 `PROCESSING → SENT`。
2. 成功后清空 `CLAIM_TOKEN`。
3. 成功后清空 `PROCESSING_STARTED_AT`。
4. 正确记录 `SENT_AT`。
5. 相同 Token 再次确认时返回 `False`。

完成后，再进入 `PROCESSING` 超时恢复与旧 Token 失效测试。

---

**截至 2026-10-19，Phase 7 已完成基础重试、重试上限、并发领取及 Claim Token 生成验证；发送确认与异常恢复机制仍在开发中。**

今天可以先停在这里。下一次继续时，从 `test_notification_valid_token.py` 开始即可。