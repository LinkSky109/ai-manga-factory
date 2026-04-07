# Phase 2 数据库设计

## 目标

Phase 2 将系统的执行单元从旧版“适配包”升级为“项目制工厂”，数据库围绕以下主线展开：

- 项目与章节推进
- 角色、场景、音色资产管理
- 可视化工作流与任务执行
- 模型路由与用量监控
- 提示词进化与共享记忆

## 核心表

### 项目与章节

- `projects`
- `project_source_materials`
- `project_story_summaries`
- `project_scripts`
- `chapters`
- `chapter_pipeline_states`

章节阶段使用固定键：

- `storyboard`
- `video`
- `voice`
- `finalize`

### 资产管理

- `character_profiles`
- `character_reference_images`
- `scene_profiles`
- `voice_profiles`

### 工作流与执行

- `workflow_definitions`
- `job_runs`
- `job_run_steps`
- `job_checkpoints`
- `artifacts`
- `artifact_archives`

`job_runs` 在 Step 5 扩展了异步执行元数据：

- `queued_at`
- `started_at`
- `finished_at`
- `locked_at`
- `last_heartbeat_at`
- `worker_id`
- `attempt_count`

### 模型路由与监控

- `provider_configs`
- `provider_usage_logs`
- `alert_records`
- `worker_heartbeats`

### 提示词进化与一致性记忆

- `prompt_templates`
- `prompt_feedback`
- `shared_memories`
- `review_tasks`

### 权限与审计

- `user_accounts`
- `access_tokens`
- `audit_logs`

## 状态机

### 项目

- `draft`
- `active`
- `blocked`
- `completed`
- `archived`

### 章节

- `not_started`
- `in_progress`
- `failed`
- `completed`

### 任务

- `queued`
- `running`
- `failed`
- `completed`

异步任务当前采用数据库队列模式：

- API 创建 `execution_mode="async"` 的任务时写入 `job_runs`
- Worker 通过 claim 机制把 `queued` 任务切到 `running`
- 失败时保留 `job_checkpoints`
- `resume` 会把任务重新置回 `queued`，由 worker 从最后 checkpoint 继续

Step 6 起，执行完成的节点会进一步生成产物索引：

- `artifacts` 保存每个已产出节点的预览文件、媒体类型、路径和元数据
- `artifact_archives` 保存归档副本、索引键与 `checksum_sha256`
- `artifact_sync_runs` 保存归档补同步队列、重试次数与失败信息

Step 7 起，项目初始化链路会继续沉淀原文与脚本资产：

- `project_source_materials` 保存导入原文、章节数与原文预览
- `project_story_summaries` 保存项目级摘要和 highlights
- `project_scripts` 保存初始化阶段生成的项目剧本初稿

Step 9-10 起，系统进一步补入团队边界和监控状态：

- `user_accounts` / `access_tokens` / `audit_logs` 支持 bootstrap token、RBAC 与审计
- `alert_records` 持久化 provider 预算告警
- `worker_heartbeats` 记录 worker 心跳与健康态

## 当前实现说明

- SQLAlchemy 模型已落地在 [apps/api/src/infrastructure/db/models](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/db/models)
- 初始化 SQL 位于 [apps/api/src/infrastructure/db/migrations/0001_initial_schema.sql](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/db/migrations/0001_initial_schema.sql)
- 异步执行运行器位于 [apps/api/src/application/services/async_job_runner.py](/Users/link/work/ai-manga-factory/apps/api/src/application/services/async_job_runner.py)
- Worker 入口位于 [apps/worker/src/entrypoints/main.py](/Users/link/work/ai-manga-factory/apps/worker/src/entrypoints/main.py)
- 当前阶段采用 `metadata.create_all()` 初始化，后续可切换到正式迁移工具
