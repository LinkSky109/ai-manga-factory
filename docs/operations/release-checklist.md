# Release Checklist

## 发布前

1. 执行 `RUN_E2E_BROWSER=1 bash /Users/link/work/ai-manga-factory/scripts/test.sh`
2. 确认 `/api/v1/monitoring/overview` 和 `/metrics` 正常
3. 确认 `AUTH_BOOTSTRAP_ADMIN_TOKEN` 已替换为正式值
4. 确认 `POSTGRES_PASSWORD`、`GRAFANA_ADMIN_PASSWORD` 已替换为正式值
5. 确认对象存储 / 网盘凭证目录已经准备好
6. 确认 `docker-compose.prod.yml` 使用的是 `.env.prod`
7. 执行 `bash /Users/link/work/ai-manga-factory/scripts/validate_prod_env.sh /Users/link/work/ai-manga-factory/infra/compose/.env.prod`
8. 执行 `bash /Users/link/work/ai-manga-factory/scripts/verify_prod_stack.sh`
9. 执行 `bash /Users/link/work/ai-manga-factory/scripts/create_release_manifest.sh`
10. 建议执行 `RUN_DEPLOY=0 RUN_SMOKE=0 RUN_BACKUP=0 bash /Users/link/work/ai-manga-factory/scripts/run_deployment_drill.sh`
11. 确认 `docker info` 可连通；如使用 `colima`，先确认 `colima start` 成功

## 发布时

1. `cd /Users/link/work/ai-manga-factory/infra/compose`
2. `bash /Users/link/work/ai-manga-factory/scripts/validate_prod_env.sh .env.prod`
3. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
4. 如需观测栈，补 `--profile observability`
5. 记录当前镜像构建时间和部署时间
6. 建议执行 `bash /Users/link/work/ai-manga-factory/scripts/check_production_endpoints.sh`
7. 建议执行 `bash /Users/link/work/ai-manga-factory/scripts/run_factory_smoke.sh`
8. 如需留档，执行 `RUN_DEPLOY=1 RUN_SMOKE=1 RUN_FACTORY_SMOKE=1 RUN_BACKUP=1 bash /Users/link/work/ai-manga-factory/scripts/run_deployment_drill.sh`

## 发布后

1. 访问 `/health`
2. 访问 `/metrics`
3. 登录 Grafana 检查 `AI Manga Factory Overview`
4. 触发一次最小任务，确认 API / worker / archive 链路正常
5. 执行一次 PostgreSQL 备份演练
6. 确认已生成 deployment drill 记录与 release manifest
