# Production Runbook

## 部署入口

- 生产 compose：`infra/compose/docker-compose.prod.yml`
- 生产环境变量模板：`infra/compose/.env.prod.example`
- 反向代理：`infra/caddy/Caddyfile`

## 首次启动

```bash
cd /Users/link/work/ai-manga-factory/infra/compose
cp .env.prod.example .env.prod
bash /Users/link/work/ai-manga-factory/scripts/validate_prod_env.sh .env.prod
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

或者：

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/deploy_prod.sh
```

发布前建议先执行：

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/verify_prod_stack.sh
bash scripts/create_release_manifest.sh
bash scripts/run_deployment_drill.sh
```

说明：

- `verify_prod_stack.sh` 现在会同时检查 `docker compose` 配置、Docker daemon 连通性和 `caddy validate`
- 如果你在 macOS 上使用 `colima`，需要先保证 `colima start` 成功，`docker info` 可访问
- 如果 Docker Desktop / Colima 下载链路不稳定，可直接使用 `bash scripts/start_lima_tuna_runtime.sh`
- `infra/compose/lima/tuna-docker-rootful.yaml` 已切到清华 Ubuntu 镜像 + 国内 registry mirror 兜底

卷策略：

- 生产 compose 默认使用命名卷 `app_data` / `app_secrets`
- 如果运行环境支持宿主机可写 bind mount，可在 `.env.prod` 中设置 `APP_DATA_MOUNT` / `APP_SECRETS_MOUNT`

默认暴露：

- Web + API 统一入口：`http://127.0.0.1:8080`
- API health：`http://127.0.0.1:8080/health`
- Metrics：`http://127.0.0.1:8080/metrics`

## 备份

优先使用本机 `pg_dump`；如果未安装且生产 compose 可用，会自动 fallback 到容器内 `postgres`。

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/backup_postgres.sh
```

可通过环境变量覆盖：

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `PGPASSWORD`
- `BACKUP_DIR`

## 恢复

优先使用本机 `psql`；如果未安装且生产 compose 可用，会自动 fallback 到容器内 `postgres`。

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/restore_postgres.sh backups/postgres/<backup.sql.gz>
```

## 故障恢复检查单

1. 确认 `api`、`worker`、`web`、`postgres`、`redis` 容器都在运行。
2. 访问 `/health`，确认 API 正常返回。
3. 访问 `/metrics`，确认监控出口正常。
4. 检查 Grafana 看板是否能读取 Prometheus。
5. 如数据库损坏，先执行最新备份恢复，再重启 `api` 与 `worker`。

## 发布后快速巡检

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/check_production_endpoints.sh
```

当 `AUTH_ENABLED=true` 时，脚本会自动优先使用 `.env.prod` 中的 `AUTH_BOOTSTRAP_ADMIN_TOKEN` 访问受保护接口；也可以手动覆盖：

```bash
cd /Users/link/work/ai-manga-factory
PROD_API_TOKEN=<admin-token> bash scripts/check_production_endpoints.sh
```

## 最小生产任务 Smoke

如果你要验证真正的业务闭环，而不只是静态端点：

```bash
cd /Users/link/work/ai-manga-factory
bash scripts/run_factory_smoke.sh
```

这个脚本会自动执行：

- 创建临时项目
- 导入样例原文并初始化
- 创建标准工作流
- 创建任务并等待完成
- 校验预览列表与第一条预览可访问
- 读取监控总览

执行完成后会在 `backups/releases/` 下生成一份 smoke 记录。

当前已验证通过的真实生产 smoke 记录：

- `backups/releases/factory-smoke-20260407-175644.md`

## 部署演练留档

如果希望把回归、配置校验、发布快照、发布后 smoke 结果自动写成一份演练记录：

```bash
cd /Users/link/work/ai-manga-factory
RUN_DEPLOY=0 RUN_SMOKE=0 RUN_BACKUP=0 bash scripts/run_deployment_drill.sh
```

如果目标环境已具备 `docker` 并且你要执行完整演练：

```bash
cd /Users/link/work/ai-manga-factory
RUN_DEPLOY=1 RUN_SMOKE=1 RUN_FACTORY_SMOKE=1 RUN_BACKUP=1 bash scripts/run_deployment_drill.sh
```
