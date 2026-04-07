# Deployment Drill Template

也可以直接执行：

```bash
cd /Users/link/work/ai-manga-factory
RUN_DEPLOY=1 RUN_SMOKE=1 RUN_FACTORY_SMOKE=1 RUN_BACKUP=1 bash scripts/run_deployment_drill.sh
```

脚本会在 `backups/releases/` 下自动生成一份带命令输出的演练记录；本模板适合补充人工观察项。

## 基础信息

- Drill Date:
- Operator:
- Env File:
- Git SHA:
- Release Manifest:

## 执行记录

1. `RUN_E2E_BROWSER=1 bash scripts/test.sh`
   - Result:
2. `bash scripts/verify_prod_stack.sh`
   - Result:
3. `bash scripts/deploy_prod.sh`
   - Result:
4. `bash scripts/check_production_endpoints.sh`
   - Result:
5. `bash scripts/run_factory_smoke.sh`
   - Result:
6. `bash scripts/backup_postgres.sh`
   - Result:

## 观测结果

- `/health`:
- `/metrics`:
- Grafana Dashboard:
- Worker Status:
- Active Alerts:

## 结论

- 是否可发布：
- 阻塞项：
- 后续动作：
