# AI 漫剧工厂

工业级 AI 漫剧生产平台，面向项目制协作、资产一致性控制、可视化流程编排、模型监控与多阶段产物交付。

## 仓库状态

当前仓库已进入工业化重构阶段：

- 新架构主路径：`apps/`、`packages/`、`infra/`、`docs/`
- 历史实现归档：`legacy_archive/`
- 当前进度：`Phase 1-4` 与 `Step 5-6` 核心链路已落地

## 顶层结构

```text
.
├── apps
│   ├── api
│   ├── web
│   └── worker
├── packages
│   ├── provider-sdk
│   ├── shared-kernel
│   ├── ui
│   └── workflow-spec
├── infra
├── docs
├── data
├── legacy_archive
└── secrets
```

## 应用职责

- `apps/api`：FastAPI 后端，负责项目、章节、资产、工作流、任务执行、监控与预览 API
- `apps/web`：Google Stitch 风格控制台，负责项目总览、资产库、流程编排和监控页面
- `apps/worker`：异步执行与断点续跑工作节点
- `packages/shared-kernel`：共享枚举、值对象、契约和通用工具
- `packages/workflow-spec`：节点编排协议、校验器和模板
- `packages/provider-sdk`：模型、音频、存储适配层
- `packages/ui`：设计令牌与组件基元

## 开发路线

1. `Phase 1`：仓库重组、最小 API/Web/Worker 入口、迁移说明
2. `Phase 2`：后端领域模型、任务执行引擎、数据库 schema
3. `Phase 3`：项目总览、章节推进、资产库、监控与预览
4. `Phase 4`：可视化编排、多智能体审核、提示词进化闭环
5. `Step 5`：真实 async worker、数据库队列、checkpoint resume
6. `Step 6`：本地预览文件、多目标归档适配层、统一预览入口、归档补同步队列

## 本地启动

### 一键启动

```bash
cd /Users/link/work/ai-manga-factory
make start
make restart
make status
make health
make logs
```

也可以直接执行：

```bash
bash scripts/run/start_services.sh
bash scripts/run/status_services.sh
bash scripts/run/health_services.sh
```

默认行为：

- 自动补齐 `apps/api/.venv`、`apps/worker/.venv`
- `apps/web/node_modules` 不存在时自动执行 `npm install`
- 后台启动 `api`、`web`、`worker`
- 日志写入 `logs/services/`

开发模式入口：

```bash
cd /Users/link/work/ai-manga-factory
make api
make web
make worker
make logs SERVICE=api LINES=20 FOLLOW=1
```

停止服务：

```bash
cd /Users/link/work/ai-manga-factory
make stop
```

查看日志：

```bash
cd /Users/link/work/ai-manga-factory
make logs
make logs SERVICE=api
make logs SERVICE=web FOLLOW=1
make logs LINES=100
```

### API

```bash
cd /Users/link/work/ai-manga-factory/apps/api
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

### Web

```bash
cd /Users/link/work/ai-manga-factory/apps/web
npm install
npm run dev
```

### Worker

```bash
cd /Users/link/work/ai-manga-factory/apps/worker
python -m venv .venv
source .venv/bin/activate
pip install -e .
python src/entrypoints/main.py --poll-interval 2
```

### 预览与归档

```bash
cd /Users/link/work/ai-manga-factory
cp .env.example .env
```

关键配置：

- `ARCHIVE_TARGETS`：归档目标列表，默认 `local-archive,object-storage`
- `OBJECT_STORAGE_MODE`：对象存储归档模式，`mirror` 或 `s3`
- `ARCHIVE_INDEX_PATH`：归档索引 manifest 文件
- `ARCHIVE_SYNC_MAX_ATTEMPTS`：归档补同步最大重试次数，默认 `3`
- `OBJECT_STORAGE_ROOT`：对象存储镜像根目录
- `OBJECT_STORAGE_BUCKET`：对象存储 bucket 名称
- `S3_ENDPOINT` / `S3_BUCKET` / `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY`：启用 `OBJECT_STORAGE_MODE=s3` 时使用
- `ARK_API_KEY`：启用 Ark 文本/视频 provider 的 API Key
- `ARK_TEXT_MODEL` / `ARK_VIDEO_MODEL`：Ark 分镜与视频默认模型
- `QUARK_PAN_MODE` / `ALIYUNDRIVE_MODE`：网盘归档模式，`mirror` 或 `api`
- `QUARK_PAN_CONFIG_DIR` / `ALIYUNDRIVE_CONFIG_DIR`：网盘 SDK 登录态目录
- `QUARK_PAN_COOKIE_FILE`：夸克 Cookie 文件路径，也支持 `AI_MANGA_FACTORY_QUARK_COOKIE`
- `QUARK_PAN_MIRROR_ROOT` / `ALIYUNDRIVE_MIRROR_ROOT`：mirror 模式下的本地镜像根目录
- `POST /api/v1/assets/artifacts/{artifact_id}/archive-sync-runs`：为指定 artifact 创建远端归档补同步任务

网盘认证准备：

```bash
cd /Users/link/work/ai-manga-factory
python3 scripts/auth_remote_storage.py --provider quark-pan --prepare-qr
python3 scripts/auth_remote_storage.py --provider quark-pan
python3 scripts/auth_remote_storage.py --provider aliyundrive
```

说明：

- Quark API 模式读取 `AI_MANGA_FACTORY_QUARK_COOKIE`、`QUARK_PAN_COOKIE_FILE` 或认证脚本落下来的 Cookie
- AliyunDrive API 模式读取 `ALIYUNDRIVE_CONFIG_DIR` 下的 SDK 登录态
- 生产运行时不执行交互式登录；worker 只消费已经准备好的凭证和登录态

### 项目初始化生产版

- `POST /api/v1/projects/{id}/initialize` 现在走真实初始化生成链
- 默认 provider 候选链为 `ark-story -> llm-story`
- 响应里的 `generation_trace` 会返回命中 provider、回退轨迹和 usage 信息
- 可选传入 `routing_mode` 与 `manual_provider` 强制指定初始化模型

### 多智能体审核自动执行

- `POST /api/v1/reviews` 现在会对 `multi-agent` 审核任务自动执行
- 默认审核 provider 候选链为 `ark-story -> llm-story`
- 审核结果会写回 `review_tasks.result_payload`
- 审核建议会自动同步到共享记忆和 prompt feedback
- 工作流编排页可查看 blocking status、命中 provider 和主要 findings

### 认证、权限、审计与配置中心

- 当 `AUTH_ENABLED=true` 或任一 `AUTH_BOOTSTRAP_*_TOKEN` 已配置时，`/api/v1/**` 会启用 Bearer Token 认证
- 当前内建角色为 `admin`、`operator`、`reviewer`、`viewer`
- `GET /api/v1/auth/me` 可查看当前身份
- `GET /api/v1/settings/overview` 与 `PATCH /api/v1/settings/providers/{provider_key}` 组成配置中心首版
- `GET /api/v1/audit-logs` 可查看关键写操作的审计记录
- 前端如果要直接访问已开启认证的 API，可在 web 环境里配置 `VITE_API_TOKEN`

推荐的本地启动方式：

```bash
AUTH_BOOTSTRAP_ADMIN_TOKEN=dev-admin-token \
VITE_API_TOKEN=dev-admin-token \
make start
```

### 监控、预算与 Worker 健康

- `GET /api/v1/monitoring/providers` 返回 provider 用量与当前阈值状态
- `GET /api/v1/monitoring/overview` 返回 provider 用量、活跃告警、worker 心跳与作业摘要
- `GET /metrics` 返回 Prometheus 文本指标
- 当 provider 累积消耗超过 `budget_threshold` 时，会生成持久化预算告警记录
- worker 会持续写入心跳，超过 `WORKER_STALE_AFTER_SECONDS` 未更新会显示为 `stale`
- 前端监控台现在可直接查看预算告警、worker 健康、路由回退与模型消耗明细

Prometheus / Grafana 可通过 profile 启动：

```bash
cd /Users/link/work/ai-manga-factory
make observability
```

默认入口：

- Prometheus: `http://127.0.0.1:9090`
- Grafana: `http://127.0.0.1:3000`
- 预置 dashboard: `AI Manga Factory Overview`

### 回归与验收入口

- 统一回归脚本：`bash /Users/link/work/ai-manga-factory/scripts/test.sh`
- Playwright smoke 列表：`cd /Users/link/work/ai-manga-factory/apps/web && npm run test:e2e:list`
- 如本机已准备浏览器，可执行：`RUN_E2E_BROWSER=1 bash /Users/link/work/ai-manga-factory/scripts/test.sh`
- demo project seed：`data/demo_projects/dpcq_chapter_seed.md`

### 生产部署骨架

- 生产 compose：`infra/compose/docker-compose.prod.yml`
- 生产环境变量模板：`infra/compose/.env.prod.example`
- 生产 compose 说明：`infra/compose/README.md`
- 反向代理与静态站点：`infra/caddy/Caddyfile`
- 环境校验脚本：`scripts/validate_prod_env.sh`
- 一键部署脚本：`scripts/deploy_prod.sh`
- 生产栈校验脚本：`scripts/verify_prod_stack.sh`
- Docker runtime 检查脚本：`scripts/require_docker_runtime.sh`
- 最小生产任务 smoke：`scripts/run_factory_smoke.sh`
- 发布快照脚本：`scripts/create_release_manifest.sh`
- 备份脚本：`scripts/backup_postgres.sh`
- 恢复脚本：`scripts/restore_postgres.sh`
- 回滚脚本：`scripts/rollback_prod.sh`
- 端点巡检脚本：`scripts/check_production_endpoints.sh`
- 运行手册：`docs/operations/production-runbook.md`
- 发布检查单：`docs/operations/release-checklist.md`
- 回滚手册：`docs/operations/rollback-runbook.md`
- 部署演练模板：`docs/operations/deployment-drill-template.md`

## 文档索引

- 架构：`docs/architecture/`
- 数据库：`docs/database/`
- 运维：`docs/operations/`
- 迁移：`docs/migration/`

## 迁移说明

旧版实现已整体迁移到 `legacy_archive/`，保留历史脚本、适配包、旧前端和共享模块，便于后续选择性复用。
