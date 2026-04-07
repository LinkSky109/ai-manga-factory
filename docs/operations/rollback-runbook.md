# Rollback Runbook

## 适用场景

- 新版本发布后 API 无法通过 `/health`
- worker 持续失败且无法恢复
- 关键页面不可用，需要回退到上一已知可用版本
- 数据异常，需要恢复到最近一次 PostgreSQL 备份

## 最小回滚

如果只是容器需要回到已有镜像状态，而不涉及数据库恢复：

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/rollback_prod.sh
```

## 带数据库恢复的回滚

如果需要把数据库恢复到指定备份：

```bash
cd /Users/link/work/ai-manga-factory
BACKUP_PATH=backups/postgres/<backup.sql.gz> bash scripts/rollback_prod.sh
```

说明：

- 该路径会先恢复数据库，再重新拉起 compose 服务
- 会覆盖当前数据库内容，执行前必须确认备份版本

## 回滚前检查

1. 确认最近一次成功备份文件存在
2. 记录当前 `/health`、`/metrics` 和错误症状
3. 保存当前 release manifest
4. 通知当前操作者暂停新的生产任务

## 回滚后检查

1. 访问 `/health`
2. 访问 `/metrics`
3. 执行 `bash scripts/check_production_endpoints.sh`
4. 检查 Grafana 的 worker 和 alert 面板
5. 触发一次最小任务 smoke
