# Async Worker 运行说明

## 目标

Step 5 起，`execution_mode="async"` 的任务不再只停留在 `queued`，而是由 `apps/worker` 轮询数据库队列并执行。

## 入口

- Worker 入口：[apps/worker/src/entrypoints/main.py](/Users/link/work/ai-manga-factory/apps/worker/src/entrypoints/main.py)
- Async runner：[apps/api/src/application/services/async_job_runner.py](/Users/link/work/ai-manga-factory/apps/api/src/application/services/async_job_runner.py)

## 本地运行

单次消费一个任务：

```bash
cd /Users/link/work/ai-manga-factory/apps/worker
python src/entrypoints/main.py --once
```

持续轮询：

```bash
cd /Users/link/work/ai-manga-factory/apps/worker
python src/entrypoints/main.py --poll-interval 2
```

## 当前行为

- 只消费 `job_runs.status = queued` 且 `execution_mode = async` 的任务
- claim 成功后任务切到 `running`
- 执行成功后写回 `completed`
- 执行失败后保留 checkpoint，可由 `POST /api/v1/jobs/{id}/resume` 重新入队

## 后续增强

- worker 心跳超时回收
- 多 worker 分布式锁
- 重试策略与死信队列
- Prometheus 队列与 worker 指标
