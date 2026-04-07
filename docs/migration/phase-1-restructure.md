# Phase 1 重构记录

## 已完成

- 新建 `apps/api`、`apps/web`、`apps/worker` 三应用骨架
- 新建 `packages/`、`infra/`、`docs/`、`tests/` 结构
- 旧实现整体迁移至 `legacy_archive/`
- 重写根 `README.md`、`Dockerfile`、`docker-compose.yml`、`.env.example`
- 建立最小可运行 FastAPI 与 React 首页

## 旧实现归档位置

- `legacy_archive/backend`
- `legacy_archive/frontend`
- `legacy_archive/modules`
- `legacy_archive/shared`
- `legacy_archive/web`
- `legacy_archive/adaptations`
- `legacy_archive/scripts`
- `legacy_archive/tests_legacy`

## 后续 Phase 2 入口

- 在 `apps/api/src/domain` 内补齐项目、资产、工作流、执行、监控领域模型
- 在 `apps/api/src/infrastructure/db` 中接入 PostgreSQL 和迁移工具
- 在 `apps/worker` 中接入断点续跑与步骤级 checkpoint
- 在 `apps/web` 中拆分项目总览、资产库、章节页与流程编排页
