# AI 漫剧工厂

## 项目定位

这个目录只保留 `ai-manga-factory` 的业务代码、运行脚本、适配包、结果沉淀和项目级前后端。

它负责：

- 漫剧生产任务创建与执行
- 小说适配包运行
- Ark 图像与视频生成接入
- 本地 API、CLI 和项目控制台
- 结果沉淀、校验报告和 job 级证据管理

它不负责：

- 多项目协作流程编排
- 外部管理模板维护
- 项目外部目录中的管理材料生产

## 当前目录

- `backend/`：FastAPI API、存储、任务执行、管理概览接口
- `frontend/`：旧版单文件控制台，保留为 `/legacy` 兜底入口
- `web/`：新版前后端分离前端工程，基于 React + TypeScript + Vite
- `modules/`：业务能力模块
- `shared/`：共享工具、结果沉淀、运行时存储和 provider 逻辑
- `scripts/`：运行、校验、建包、导入原文脚本
- `adaptations/`：小说适配包与报告
- `docs/`：项目文档
- `agents/`：项目内角色配置
- `data/`：运行时数据目录
- `secrets/`：本地密钥目录

## 前后端分离架构

当前项目已经工程化为“后端 API + 独立前端工程”的结构：

- 后端：`FastAPI`
- 前端：`web/` 下的 `React + TypeScript + Vite`
- 结果绑定：`GET /adaptation-packs/{pack_name}/latest-result` 返回显式 `job_id` 绑定，避免共享报告误引用
- 兼容策略：旧版页面继续保留在 `/legacy`
- 控制台增强：最近任务区支持直接复跑历史任务，适合低成本验路和结果重算
- 控制台增强：最近任务区会优先置顶运行中的任务，并支持按能力筛选
- 控制台增强：能力筛选会同步到地址栏 `?capability=`，刷新后仍可恢复当前视角
- 控制台增强：任务状态筛选支持 `?jobStatus=running|completed|failed`，便于直接打开运行中或失败视角
- 控制台增强：最近任务支持按项目名、source、target、pack、summary 关键词搜索，并同步到 `?jobSearch=`

## 环境准备

先准备 Python 环境：

```powershell
python -m venv E:\work\.venvs\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe -m pip install -r requirements.txt
```

再准备前端依赖：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory\web
& "C:\Program Files\nodejs\npm.cmd" install
```

## 启动方式

统一入口：

```powershell
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py backend
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py web
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py build-web
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py health --base-url http://127.0.0.1:8000
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py all
```

说明：
- `backend` 启动 FastAPI 后端
- `web` 启动 Vite 前端开发服务
- `build-web` 构建前端静态资源
- `health` 检查关键接口是否在线
- `all` 同时启动前后端，适合本地开发联调

启动后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\run_backend.ps1
```

开发模式再开一个终端启动前端：

```powershell
E:\work\project-manager\workhome\projects\ai-manga-factory\start_web.bat
```

访问入口：

- 新版前端：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000`
- 后端直出构建版前端：`http://127.0.0.1:8000/`
- 旧版控制台：`http://127.0.0.1:8000/legacy`

说明：新版前端优先承担项目运行控制台职责，旧版控制台暂时保留任务创建与部分操作型表单。

如果要让后端直接服务新版前端，先构建：

```powershell
E:\work\project-manager\workhome\projects\ai-manga-factory\build_web.bat
```

## 常用脚本

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\create_adaptation_pack.py --pack-name dpcq_ch1_20 --source-title "斗破苍穹" --chapter-start 1 --chapter-end 20
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\build_source_url_manifest.py --pack-name dpcq_ch1_20 --force
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\collect_source_text.py --pack-name dpcq_ch1_20 --source-dir E:\novels\dpcq_chapters --chapter-start 1 --chapter-end 20 --overwrite
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\playwright_source_capture.py login --pack-name dpcq_ch1_20 --config-file adaptations\dpcq_ch1_20\source\playwright_capture.template.json
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\playwright_source_capture.py capture --pack-name dpcq_ch1_20 --url-manifest adaptations\dpcq_ch1_20\source\incoming\source_urls.json --wait-selector "body"
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_source_ingestion_pipeline.py --pack-name dpcq_ch1_20 --toc-file E:\novels\dpcq_catalog.html --base-url "https://www.qidian.com"
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\generate_chapter_briefs.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 20 --force
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20 --real-images
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\validate_job_output.py --pack-name dpcq_ch1_20
```

如需自定义 Python 路径，可设置：

```powershell
$env:AI_MANGA_FACTORY_PYTHON="D:\your-path\python.exe"
```

## 使用说明

- [AI漫剧工厂操作手册](docs/AI漫剧工厂操作手册.md)
- [小说原文导入工具](docs/小说原文导入工具.md)
- [Playwright 正版原文抓取](docs/Playwright正版原文抓取.md)
- [原文获取工具调研](docs/原文获取工具调研.md)
- [AI漫剧工厂使用说明](docs/ai-manga-factory-使用说明.md)
- [前后端分离工程化架构](docs/前后端分离工程化架构.md)

## 鍏抽敭楠岃瘉

部署或重启后，先执行：

```powershell
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py verify-deploy --base-url http://127.0.0.1:8000
```

这会核对 `/health`、`/openapi.json`、`/artifacts-index`、`/jobs/summary`，并检查 OpenAPI 里是否包含关键运行时路由，专门用来收口 `runtime-source-drift`。

需要跑低成本浏览器 smoke 时，执行：

```powershell
python E:\work\project-manager\workhome\projects\ai-manga-factory\start_project.py smoke-browser --app-url http://127.0.0.1:8000
```

这会直接调用 `scripts/run_frontend_real_media_smoke.mjs`，是当前最明确的浏览器 smoke 入口。

`check_api.py` 和 `run_test_report.py` 现在也会使用同一套 runtime 核对逻辑，分别用于快速检查和生成报告。

## 资产锁前移与标准化资产卡

当前 pack 模式下，资产锁已经从单纯的提示词约束前移到完整的章节生产链路。对启用了 `asset_lock.json` 的适配包，章节生产会同时加载：

- `adaptations/<pack>/asset_lock.json`
- `adaptations/<pack>/assets/characters/character_cards.json`
- `adaptations/<pack>/assets/scenes/scene_cards.json`

这三类文件分别承担不同职责：

- `asset_lock.json`：角色固定 prompt、音色映射、参考图路径、场景基线。
- `character_cards.json`：标准化角色卡，补充 `dramatic_role`、`visual_traits`、`asset_status`、`reference_assets` 等结构化字段。
- `scene_cards.json`：标准化场景卡，补充 `baseline_prompt`、`asset_status`、`reference_assets`、镜头约束与环境基线。

注意：

- `主角 / 同伴 / 对手 / 旁白` 这类槽位不再作为正式流程字段传递。
- 分镜、音频、QA 和 manifest 里应直接使用真实角色名。
- 槽位词只允许存在于历史兼容逻辑或旧数据里，不能进入新的章节中间产物。

## 章节 JSON 流水线

pack 模式章节运行时，章节目录现在会产出一条明确的 JSON 流水线：

- `story_grounding.json`：章节事实源，提取真实角色、场景锚点、世界规则、候选对白与有效旁白。
- `storyboard_blueprint.json`：内容驱动的镜头蓝图，确定时长、镜头数、关键帧数、对白角色和出镜角色。
- `storyboard.json`：最终分镜表，只保留真实 canonical character。
- `audio_plan.json`：只消费真实角色分镜，生成对白/旁白轨、总线、优先级和 ducking 参数。

其中 `story_grounding.json` 和 `storyboard_blueprint.json` 是后续 QA、复跑和问题定位的首选检查入口。

## 章节时长计划与可审阅资产库

当前 pack 模式支持两层章节时长配置：

- `adaptations/<pack>/pack.json` 中的 `default_target_duration_seconds`
- `adaptations/<pack>/chapter_briefs.json` 中每章的 `target_duration_seconds`

运行 pack 任务时，系统会把章节级时长整理成 `chapter_duration_plan` 注入 job input，并优先用于 `storyboard_blueprint.json` 的 `target_duration_seconds` 规划。

标准化资产卡也补充为可审阅状态，不再只看占位图：

- `character_cards.json` 新增并维护 `asset_status_detail`、`review_status`、`approval_notes`、`owner`、`review_checklist`、`source_evidence`、`last_verified_job_id`、`usage_scope`
- `scene_cards.json` 同样维护上述审阅字段，并继续保留 `camera_guardrails`、`continuity_guardrails`

pack 结果沉淀已切到外部 runtime 目录，不再继续回写 `adaptations/<pack>/reports/`。当前应优先查看：

- `C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory\artifacts\job_<id>`
- `C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory\artifacts\pack_reports\<pack>\reports`
