# Monitoring & Alerts

## 当前能力

- `GET /api/v1/monitoring/providers`
  - 返回 provider 用量汇总与阈值状态
- `GET /api/v1/monitoring/overview`
  - 返回 provider 用量
  - 返回活跃预算告警
  - 返回 worker 心跳与健康态
  - 返回作业队列摘要
- `GET /metrics`
  - 返回 Prometheus 标准文本指标

## 预算告警

- 告警源于 provider 累积消耗与 `budget_threshold` 的对比
- 当前规则：
  - `consumed < threshold`：不告警
  - `consumed >= threshold`：`warning`
  - `consumed >= threshold * 1.2`：`critical`
- 告警会持久化到 `alert_records`
- 当后续监控查询发现消耗回落到阈值以下时，会把对应告警标记为 `resolved`

## Worker 心跳

- worker 在启动、空闲轮询、消费任务、退出时都会写入心跳
- 心跳写入 `worker_heartbeats`
- `WORKER_STALE_AFTER_SECONDS` 控制陈旧判定窗口，默认 `30`
- 当前健康态：
  - `healthy`
  - `stale`
  - `stopped`

## 本地验证

```bash
cd /Users/link/work/ai-manga-factory/apps/api
.venv/bin/python -m unittest tests.integration.test_monitoring_api -v

cd /Users/link/work/ai-manga-factory/apps/web
npm run build
```

## Observability Stack

- Prometheus 配置：`infra/prometheus/prometheus.yml`
- Grafana datasource provisioning：`infra/grafana/provisioning/datasources/prometheus.yml`
- Grafana dashboard provisioning：`infra/grafana/provisioning/dashboards/dashboard.yml`
- 预置 dashboard：`infra/grafana/dashboards/ai-manga-factory-overview.json`

启动：

```bash
cd /Users/link/work/ai-manga-factory
make observability
```
