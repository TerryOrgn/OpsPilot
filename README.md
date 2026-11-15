# OpsPilot JOB Monitor v1

Python + MySQL 8 + APScheduler 3。失败/超时检测、告警去重与恢复、事务内通知、CONSOLE 发送、三次失败耗尽及崩溃回收。

## 本地验收

在项目根目录运行：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python run_job_acceptance.py
```

入口强制 `MYSQL_DATABASE=opspilot_test` 和 `OPSPILOT_EXPECTED_DATABASE=opspilot_test`，每个连接执行 `SELECT DATABASE()`，不匹配立即关闭。使用现有测试表结构；不会自动创建/清空数据库。测试以 UUID 创建数据并清理，全链路使用独立 checkpoint，扫描结果限定本次 JOB。不要使用全目录 pytest discovery：历史 live 测试不属于本入口安全范围。

## 运行服务

参考 [部署与运维手册](docs/JOB_RUNBOOK.md)。JOB v1 唯一服务入口为 `scheduler.py`，同时运行监控与通知任务。不要同时启动旧 `notification_scheduler.py` 或其他通知 Worker。

## 交付边界

CONSOLE 通知是至少一次投递：输出后进程崩溃、确认前连接失败可能导致重复输出；token 防止旧 Worker 更新状态，不能撤销已发生的外部发送。失败计数包括发送失败和 PROCESSING 超时，累计三次进入 EXHAUSTED，成功不会重置已有失败次数。

### 本地 JOB 告警 AI 分析

按需分析需要额外安装 OpenAI Python SDK（验收版本：`python -m pip install openai==3.37.0`）。
在本地 `.env` 设置 `OPENAI_API_KEY` 和 `OPSPILOT_JOB_AI_MODEL`。
使用 DeepSeek 时，同时设置 `OPENAI_BASE_URL=https://api.deepseek.com`，模型可设为 `deepseek-flash`。
重启看板，在 `opspilot_test` 创建失败 JOB 并运行监控，然后点击「AI 分析所选 JOB 告警」。
模型只接收行号和状态，原因和建议用于辅助排查。模型不可用时页面仍保留已知事实。
