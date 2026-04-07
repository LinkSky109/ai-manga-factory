# AI 漫剧工厂工业化推进蓝图

## 目标

把当前已经完成 `Phase 1-4` 的仓库，继续推进到可稳定运行、可监控、可恢复、可扩展的工业级“AI 漫剧工厂”。

## 当前基线

已完成：

1. `Phase 1`：新 monorepo 骨架、旧系统归档、API/Web/Worker 最小入口
2. `Phase 2`：项目制数据库模型、项目/章节/资产/工作流/任务执行主链路
3. `Phase 3`：项目总览、章节推进、资产库、监控与预览控制塔
4. `Phase 4`：工作流编排页、提示词进化页、共享记忆、审核任务 API

未完成的核心能力：

- 真实异步任务执行
- 对象存储/网盘归档闭环
- 流媒体预览服务
- 小说原文到剧本的项目初始化链路
- 多智能体审核自动执行
- 认证、权限、审计、限流
- 生产级监控告警与恢复流程
- E2E/回归/性能/部署验收

## 推进原则

- 每一步都要保持后端测试通过、前端构建通过
- 优先补齐“真实生产链路”，再做体验增强
- 先做单机稳定，再做分布式扩展
- 先保留接口兼容，再逐步替换占位能力

## 依赖图

```text
Step 5 -> Step 6 -> Step 8 -> Step 10 -> Step 12
Step 5 -> Step 7 -> Step 8 -> Step 11
Step 5 -> Step 9 -> Step 10 -> Step 12
Step 6 -> Step 11
```

## 阶段计划

### Step 5：异步执行引擎落地

状态：`completed`

目标：

- 让 `apps/worker` 从占位程序升级为真实执行器
- 把 `execution_mode="async"` 接到可消费队列
- 支持任务排队、状态更新、失败重试、断点恢复

已交付：

- `apps/api` 新增共享执行 runtime，sync/async 共用同一套节点执行落库逻辑
- `job_runs` 增加队列元数据与 worker claim 信息
- `apps/worker` 升级为可轮询数据库队列的真实 worker 入口
- `resume` 支持 async 任务重新入队并从 checkpoint 恢复
- 前端控制塔在存在 active job 时自动轮询刷新

范围：

- 接入 Redis 队列或数据库队列
- Worker 消费 `job_runs`
- 记录每个节点执行日志和 checkpoint
- 支持 `resume` 从最后失败节点继续
- 前端任务状态从“同步即时结果”升级为“轮询真实状态”

写入范围：

- `apps/worker/src/**`
- `apps/api/src/application/services/job_service.py`
- `apps/api/src/infrastructure/queue/**`
- `apps/api/src/api/routes/jobs.py`

验证：

- 新增 async job 集成测试
- 失败节点恢复测试
- 手工验证 `POST /api/v1/jobs` async 模式能被 worker 消费

退出标准：

- async 任务可以从 queued -> running -> completed/failed
- resume 能从 checkpoint 继续

回滚：

- 保留 sync 路径可用
- 异步调度失败时可降级为 sync

### Step 6：产物归档与预览服务落地

状态：`in_progress`

目标：

- 让视频/音频/图片产物进入统一归档目录和对象存储/网盘
- 让预览页不再是占位，而是可播放真实产物

范围：

- 建 `artifacts` 与 `artifact_archives` 表
- 产物写入本地目录、对象存储、网盘同步器
- 为图片/音频/视频生成预览元数据
- 增加预览下载/流式播放接口
- 前端预览页支持播放真实资源

当前进展：

- 已落地 `artifacts` / `artifact_archives` 数据模型
- 已补 `artifact_sync_runs` 队列表，支持远端归档补同步任务入队和 worker 消费
- 已把 archive sync 状态并入 artifact 读模型，前端预览页可直接看到最新补同步结果
- 已为产物与归档副本写入 `checksum_sha256`，并同步进 manifest 索引
- 已为 archive sync queue 增加自动重试上限，失败任务会在阈值内重排，超限后落为 `failed`
- 已为 `object-storage` 加入可切换的 `s3` 远端上传模式，保留 `mirror` 作为默认稳定路径
- 已接入 `ark-story` / `ark-video` / `ark-image` provider，并恢复多供应商候选链与失败回退能力
- 已把 step 级 provider 候选链、尝试历史与最终命中写入 `output_snapshot`
- 已在前端监控台展示最近路由路径、fallback 记录和失败停靠点
- 已接通本地归档、副本索引和 `/api/v1/previews/artifacts/{id}` 访问入口
- 已让前端预览页嵌入真实 HTML/WAV 预览资源
- 已把归档层升级为 `local-archive` / `object-storage` 多目标 adapter，并写入 manifest 索引
- 已补 artifact 查询接口与 `quark-pan` / `aliyundrive` mirror adapter 注册表
- 已补 `storage target` 可视化和 `artifact archive resync` 路径
- 已补 `storage target readiness` 与项目级批量 resync
- 已让 worker 在 async job 之后继续轮询 archive sync 队列
- 已接入真实 Quark / AliyunDrive SDK 模式，并恢复老项目的凭证目录 / cookie 文件方案
- 已补独立认证脚本，服务运行时只消费已有凭证与登录态
- 尚未生成真实视频编码/HLS 资源

写入范围：

- `apps/api/src/infrastructure/storage/**`
- `apps/api/src/application/queries/preview.py`
- `apps/api/src/api/routes/previews.py` 或 `projects.py`
- `apps/web/src/pages/preview/**`

验证：

- 单元测试：归档记录、索引写入
- 集成测试：完成 job 后能返回 preview item
- 手工验证：预览页可打开真实图片/音频/视频

退出标准：

- job 完成后至少生成 1 个真实预览资源
- 归档状态在前端可见

### Step 7：项目初始化生产线

状态：`completed`

目标：

- 从“项目已存在”升级到“可导入原文并初始化项目”

范围：

- 小说原文导入
- 原文摘要
- 剧本提取
- 角色/场景资产初稿生成
- 项目总览页出现初始化状态与进度

当前进展：

- 已新增 `project_source_materials` / `project_story_summaries` / `project_scripts` 数据模型
- 已接通 `POST /api/v1/projects/{id}/initialize` 与 `GET /api/v1/projects/{id}/initialization`
- 已实现“原文导入 -> 摘要 -> 剧本 -> 章节草稿 -> 角色/场景初稿”初始化编排
- 已把初始化链路切到真实 provider 候选链，默认 `ark-story -> llm-story`
- 已把模型命中结果、回退轨迹、usage 信息写入 `generation_trace`
- 已在项目总览页展示初始化阶段卡片、原文预览、摘要、剧本和初稿资产摘要
- 已在项目总览页展示初始化 provider、生成模式与回退轨迹
- 已在资产页补入场景资产草稿列

写入范围：

- `apps/api/src/domain/project/**`
- `apps/api/src/application/orchestrators/**`
- `apps/api/src/api/routes/projects.py`
- `apps/web/src/pages/dashboard/**`

验证：

- 导入 demo 小说后能自动生成 project/chapter/asset 初稿
- 项目初始化状态能在总览页展示
- Ark 可用时返回模型生成摘要/剧本/角色/场景
- Ark 失败时自动回退到 `llm-story`

退出标准：

- 可以从原文启动一个新项目，而不是手工逐条录入

### Step 8：多智能体审核自动执行

状态：`completed`

目标：

- 审核任务不再只是记录，而是能真实运行审核工作流

范围：

- 剧本审核、分镜审核、人物一致性审核
- 审核结果写入 `review_tasks`
- 审核建议同步到共享记忆和提示词优化建议
- 前端编排页显示审核结果与阻塞状态

当前进展：

- 已把 `POST /api/v1/reviews` 升级为“创建即执行”的多智能体审核入口
- 已接通 `ark-story -> llm-story` 的审核 provider 候选链与自动回退
- 已把审核结果、阻塞状态、命中 provider 与回退轨迹写入 `review_tasks.result_payload`
- 已把审核建议自动同步到 `shared_memories`
- 已把审核建议自动同步到 `prompt_feedback`
- 已在工作流编排页展示审核状态、阻塞状态、命中 provider 与核心 findings

写入范围：

- `apps/api/src/application/services/review_service.py`
- `apps/api/src/infrastructure/agents/**`
- `apps/api/src/api/routes/reviews.py`
- `apps/web/src/pages/workflow-editor/**`

验证：

- 创建 multi-agent review 后会自动完成审核执行
- Ark 可用时审核链路命中 `ark-story`
- Ark 失败时自动回退到 `llm-story`
- 审核结果会生成 shared memory 与 prompt feedback
- 编排页可直接看到审核 blocking status 和 findings
- 可以触发一次 review run
- review run 产出 findings、severity、recommendation
- findings 能回流到记忆/进化页

退出标准：

- 审核模块成为真实生产质量门，而不是纯展示数据

### Step 9：认证、权限、审计与配置中心

状态：`completed`

目标：

- 把系统从“单人开发台”推进到“团队可用后台”

范围：

- 登录与会话
- RBAC：管理员、制片、审核、操作员
- 审计日志
- 提供商密钥配置
- 限流和危险操作保护

写入范围：

- `apps/api/src/core/security.py`
- `apps/api/src/api/routes/auth.py`
- `apps/api/src/infrastructure/db/models/**`
- `apps/web/src/pages/settings/**`

验证：

- 未登录不可访问敏感接口
- 关键写操作有审计记录
- provider 配置可视化可修改
- 设置中心可查看当前身份、bootstrap 账户、运行配置、provider 开关与审计日志

退出标准：

- 管理后台具备基本团队使用边界

### Step 10：监控、预算与告警体系

状态：`completed`

目标：

- 把“看到数据”升级为“能发现风险并报警”

范围：

- Prometheus 指标
- Grafana 看板
- provider 预算阈值告警
- worker 健康检查
- 队列积压、失败率、恢复次数监控

当前进展：

- 已新增 `/api/v1/monitoring/overview` 聚合接口
- 已把 provider 阈值告警持久化到 `alert_records`
- 已把 worker 心跳持久化到 `worker_heartbeats`
- 已在监控台展示活跃告警、worker 健康、队列摘要和路由回退
- 已补 Step 10 集成测试，覆盖预算告警与陈旧 worker 判定
- 已新增 `/metrics` Prometheus 指标出口
- 已补 `infra/prometheus` 抓取配置
- 已补 `infra/grafana` datasource provisioning、dashboard provisioning 与首版运营看板

写入范围：

- `infra/prometheus/**`
- `infra/grafana/**`
- `apps/api/src/infrastructure/observability/**`
- `apps/web/src/pages/monitoring/**`

验证：

- 指标可采集
- 面板可看见 job/provider/queue 状态
- 阈值超过后能触发告警记录

退出标准：

- 系统具备基础 SRE 可观测能力

### Step 11：验收测试与回归体系

状态：`completed`

目标：

- 让后续每次改动都不容易把工厂链路打坏

范围：

- API 集成测试扩展
- Playwright E2E
- 样例项目 seed
- 回归快照
- 构建/类型/测试统一脚本

当前进展：

- 已新增 `scripts/test.sh`，统一执行 API 回归、Web build、Playwright smoke 列表
- 已新增 Playwright 配置与首条控制塔 smoke 用例
- 已为关键页面补 `data-testid`，稳定 smoke 选择器
- 已补 demo project seed：`data/demo_projects/dpcq_chapter_seed.md`
- 已改为优先复用本机 `Microsoft Edge`，真实浏览器 smoke 已跑通

写入范围：

- `apps/api/tests/**`
- `apps/web/tests/e2e/**`
- `tests/smoke/**`
- `scripts/test.sh`

验证：

- 关键主流程有 E2E 覆盖
- 至少有一套 demo project 可一键验证

退出标准：

- 每个阶段都可以重复验证，不靠手工记忆

### Step 12：部署、备份与生产运行手册

状态：`completed`

目标：

- 从“开发环境可跑”推进到“正式环境可部署、可恢复”

范围：

- Docker Compose 生产版
- Caddy/Nginx 反向代理
- 数据备份与恢复
- 对象存储凭证说明
- 故障恢复 Runbook
- 发布 checklist

当前进展：

- 已新增 `infra/compose/docker-compose.prod.yml`
- 已新增 `infra/compose/.env.prod.example`
- 已新增 `infra/caddy/Caddyfile`
- 已补 `web-runtime` Docker target，用于生产静态站点与反向代理镜像
- 已修正 worker 生产镜像，把 `apps/api/src` 一并打进容器
- 已为生产 compose 增加基础 healthcheck 和依赖顺序
- 已新增 `.dockerignore`，避免把本地 runtime/secret 垃圾打进镜像上下文
- 已新增 PostgreSQL 备份 / 恢复脚本
- 已新增生产端点巡检脚本，并覆盖认证与受保护 API
- 已新增最小生产任务 smoke 脚本，覆盖项目初始化、工作流、async job、预览与监控闭环
- 已新增 `.env.prod` 校验脚本与一键部署脚本
- 已新增发布快照脚本与回滚脚本
- 已新增自动化部署演练留档脚本，可把回归、校验、发布快照、smoke 结果写入记录
- 已新增 production compose 使用说明与发布检查单
- 已新增生产运行手册：`docs/operations/production-runbook.md`
- 已新增回滚手册与部署演练模板
- 已新增 `scripts/start_lima_tuna_runtime.sh` 与 `infra/compose/lima/tuna-docker-rootful.yaml`
- 已把 Docker build 链切到“清华 Debian + 清华 PyPI + npmmirror npm + daemon registry mirror”稳定路径
- 已修复 Caddy 路由顺序，确保 `/health`、`/metrics`、`/api/*` 先于 SPA fallback 代理
- 已把 production compose 默认数据卷切到 `app_data` / `app_secrets` 命名卷，避免 Lima 只读宿主挂载导致产物写入失败
- 已在真实 Lima Docker runtime 上完成生产部署、端点巡检与工厂 smoke
- 已产出最新真实 smoke 记录：`backups/releases/factory-smoke-20260407-175644.md`

写入范围：

- `infra/compose/**`
- `infra/caddy/**`
- `docs/operations/**`
- `README.md`

验证：

- 一套全新环境可以启动 API/Web/Worker/Postgres/Redis
- 备份恢复文档可执行
- 真实 Docker Compose 生产栈已跑通，`check_production_endpoints.sh` 通过
- 真实工厂生产 smoke 已通过，覆盖项目初始化、async job、预览与监控闭环

退出标准：

- 项目进入“可交付、可演示、可试运行”状态

## 并行边界

可以并行：

- `Step 6` 的对象存储归档 与 `Step 7` 的项目初始化链路
- `Step 9` 的权限/审计 与 `Step 10` 的监控看板
- `Step 11` 的 E2E 与 `Step 12` 的部署文档

不要并行：

- `Step 5` 与任何会大改 `job_runs` 状态机的任务
- `Step 8` 与任何会重写 review 数据模型的任务

## 反模式清单

- 在 async worker 未稳定前大量扩展 UI 轮询逻辑
- 把真实执行逻辑塞回前端
- 在没有审计前开放敏感 provider 配置写接口
- 先做华丽工作流画布，后补真实持久化
- 不做 seed/demo project 就推进 E2E

## 下一执行步

从 `Step 5：异步执行引擎落地` 开始。

原因：

- 它是后续归档、预览、审核自动执行、监控告警的共同前置
- 当前系统最大的“工业化缺口”就是 async 仍是占位

## Step 5 首轮细分任务

1. 引入队列抽象和 worker 消费入口
2. 让 async job 真正入队
3. worker 消费后更新 `job_runs` / `job_run_steps`
4. 失败后写 checkpoint 并支持恢复
5. 补 async 集成测试
6. 前端任务状态轮询接入 async 状态
