# Learnings

## [LRN-20260329-007] best_practice

**Logged**: 2026-03-29T23:05:00+08:00
**Priority**: high
**Status**: pending
**Area**: screenplay-qa

### Summary
`ai-manga-factory` 在为重复分镜补差异化台词或旁白时，文案必须始终留在故事世界内，不能把“继续往前推”“这一拍别复述”这类制作指令式语言漏进最终 `storyboard`、`audio_plan`、`voice_script` 和成片字幕。

### Details
本轮在 `job_42` 的真实 runtime 产物里发现，重复镜头虽然已打散，但空对白镜头被补成了元指令式文案，例如：
- `别停在同一个反应上，继续往前推。`

这类文本会直接破坏成片沉浸感，也会让“画面-字幕-配音一致”退化成“技术上一致但内容失真”。修复后：
- `_build_variation_dialogue()` 改为输出世界内台词/旁白
- `_build_variation_hint()` 改为输出世界内视觉变化
- `_review_plan()` 新增门禁，拦截对白或旁白中的制作指令

### Suggested Action
后续默认遵循：
1. 任何为避免重复而补出的对白、旁白、视觉提示，都必须是角色世界内表达，不得出现制作术语或导演指令。
2. QA 默认检查 `storyboard` 行级对白/旁白和 `voice_script`，一旦出现元指令文案直接阻断交付。
3. 视觉变体优先写成“视线变化 / 压迫感变化 / 环境异兆变化”，不要再写抽象流程词。

### Metadata
- Source: implementation
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\modules\manga\chapter_factory.py, E:\work\project-manager\workhome\projects\ai-manga-factory\tests\test_manga_chapter_factory.py
- Tags: qa, screenplay, dialogue, narration, immersion, storyboard

---

## [LRN-20260329-006] user_preference

**Logged**: 2026-03-29T22:32:25+08:00
**Priority**: high
**Status**: pending
**Area**: manga-quality-bar

### Summary
`ai-manga-factory` 的视频成片必须做到画面、字幕、配音严格一致；不能出现画面和旁白/台词不对应，背景音乐也必须遵守音频设计。当前项目的内容与导演风格参考《怪谈玩家，但画风不对》，长远目标是向《进击的巨人》级别的动漫制作水准靠拢。

### Details
用户明确补充了当前项目的质量要求与长期目标：
- 当前交付要求：
  - 画面必须和字幕、配音逐镜头一致
  - 不能出现旁白、台词和画面脱节
  - 背景音乐必须遵守音频设计，不再只做情绪占位
- 当前成片参考：
  - 《怪谈玩家，但画风不对》
- 长期目标参考：
  - 《进击的巨人》
  - 对齐方向包括：画面、配音、配乐、导演调度

这意味着后续不只要检查“文件是否生成”和“时长是否闭环”，还要把音画一致性、字幕对白一致性、BGM 是否服从音频设计、导演节奏与镜头语言质量纳入主 QA 标准。

### Suggested Action
后续默认遵循：
1. 把“画面-字幕-配音一致性”提升为章节级硬门禁，而不是软性建议。
2. 把“背景音乐是否遵守音频设计”加入音频计划与最终 QA 的显式检查项。
3. 分镜、配音、配乐、导演节奏的调优优先参考《怪谈玩家，但画风不对》的当前风格目标。
4. 长期把《进击的巨人》作为上限标杆，逐步收口画面表现、声优表现、配乐层次和导演调度。

### Metadata
- Source: user_feedback
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\modules\manga\chapter_factory.py, E:\work\project-manager\workhome\projects\ai-manga-factory\tests\test_manga_chapter_factory.py
- Tags: qa, storyboard, subtitles, dubbing, bgm, directing, quality-bar

---

## [LRN-20260326-005] best_practice

**Logged**: 2026-03-26T23:20:00+08:00
**Priority**: high
**Status**: pending
**Area**: cloud-delivery

### Summary
网盘同步这类长耗时交付动作，默认走后台任务，并在前端直接展示队列、状态和重试入口。

### Details
这次给 `ai-manga-factory` 补云端交付时，单任务和批量任务如果在 HTTP 请求里同步执行，会拖到请求超时，而且用户在页面里看不到“正在同步 / 已完成 / 失败重试”的状态。改成“真同步入后台队列，dry-run 同步返回计划，前端显示交付队列和重试入口”后，在线接口可以立即返回，页面也能直接反映同步进度和结果。

### Suggested Action
1. 任何可能超过普通交互时长的云端交付动作，默认做成后台任务。
2. `dry-run` 保持同步返回，用于快速查看计划。
3. 页面至少要同时提供概览、队列状态和失败重试入口，不把交付状态藏在终端日志里。

### Metadata
- Source: implementation
- Related Files: backend/main.py, backend/schemas.py, web/src/App.tsx, web/src/types.ts, web/src/styles.css
- Tags: cloud-sync, async, queue, frontend, delivery

---

## [LRN-20260326-001] best_practice

**Logged**: 2026-03-26T01:12:00+08:00
**Priority**: high
**Status**: resolved
**Area**: media-pipeline

### Summary
真实视频能力要以“可收口”为第一原则：资产级进度回写、限时等待、超时自动回退本地镜头，三者缺一不可。

### Details
这次 `job_33` 证明，单纯恢复 `report_progress` 还不够；如果图生视频按 asset 串行长时间轮询，整章交付仍会被外部模型吞掉时间预算。把真实视频链改成“asset 级 heartbeat + 120 秒超时 + 自动回退本地镜头”后，`job_34` 从前端入口完整完成，并保留了真实图片、音频脚本、章节视频和 QA 产物。

### Suggested Action
后续凡是接入外部媒体生成能力，都默认采用相同策略：
- 进入外部调用前先回写当前 asset 进度
- 设置明确等待上限
- 超时后立即回退到可交付的本地方案
- 在最终摘要里写清回退比例和原因

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, shared/providers/ark.py, scripts/run_frontend_real_media_smoke.mjs
- Tags: media, fallback, progress, qa, reliability
- Pattern-Key: media.external_generation_should_have_bounded_wait_and_fallback

### Resolution
- **Resolved**: 2026-03-26T01:12:00+08:00
- **Notes**: `job_34` 已完成；真实视频超时不再阻塞整章任务收口。

---

## [LRN-20260326-003] user_preference

**Logged**: 2026-03-26T22:35:00+08:00
**Priority**: high
**Status**: promoted
**Area**: artifact-viewer

### Summary
`ai-manga-factory` 的产物页必须直接展示网盘同步状态、远程路径和操作入口，不能再依赖终端日志确认。

### Details
用户已经把业务产物同步到夸克网盘和阿里云盘，并明确要求在前端产物页中看到“网盘同步状态 / 同步路径 / 打开网盘目录”这类信息。说明产物阅读器不仅要预览本地文件，还要承担交付定位职责，帮助直接判断某个产物是否已进入云端以及该去哪里找。

### Suggested Action
后续默认遵循：
1. 产物页优先展示每个网盘 provider 的同步状态、最近同步时间、远程目录和远程文件路径。
2. 页面提供至少两个可操作入口：打开网盘主页、复制目录/文件路径。
3. 对没有同步记录的产物，页面直接显示“未同步”而不是让用户回到终端排查。

### Metadata
- Source: user_feedback
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\backend\main.py, E:\work\project-manager\workhome\projects\ai-manga-factory\backend\schemas.py, E:\work\project-manager\workhome\projects\ai-manga-factory\web\src\App.tsx
- Tags: artifacts, cloud-storage, quark-pan, aliyundrive, frontend, delivery

---

## [LRN-20260326-004] best_practice

**Logged**: 2026-03-26T22:52:00+08:00
**Priority**: high
**Status**: promoted
**Area**: cloud-delivery

### Summary
`ai-manga-factory` 的云端交付能力应默认做成“可操作”的工作流，不只显示同步状态，还要允许从任务详情直接触发同步。

### Details
仅展示夸克网盘和阿里云盘的同步结果还不够，实际使用时用户需要在确认任务完成后立刻执行云端交付，而不是再切回终端运行脚本。因此任务详情页应直接具备“生成同步计划 / 同步到全部网盘 / 同步到指定 provider”的能力，并在操作后自动刷新状态。

### Suggested Action
后续默认遵循：
1. 云端同步相关能力优先落到任务详情或产物详情，避免要求用户回到命令行。
2. 同步动作完成后，自动刷新总览、任务和产物页的状态。
3. 页面至少同时提供“状态查看”和“动作触发”两类入口，避免做成只能看不能用的监控板。

### Metadata
- Source: implementation
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\backend\main.py, E:\work\project-manager\workhome\projects\ai-manga-factory\web\src\App.tsx
- Tags: cloud-storage, delivery, task-detail, frontend, workflow

## [LRN-20260326-003] user_preference

**Logged**: 2026-03-26T21:30:00+08:00
**Priority**: high
**Status**: promoted
**Area**: encoding

### Summary
`ai-manga-factory` 项目内所有文本文件统一使用 UTF-8 编码，无 BOM。

### Details
用户明确要求项目文件统一采用 UTF-8。后续处理源码、脚本、配置、文档和同步报告时，优先保证文件字节层为 UTF-8；如果终端显示乱码，应先验证文件字节和 Unicode 内容，不要误判为文件仍需再次转码。

### Suggested Action
1. 项目内新增或改写文本文件时默认使用 UTF-8 无 BOM。
2. 发现乱码时先用 Python 直接以 `utf-8` 读取验证，再决定是否需要转码。
3. 对外部抓取会话、浏览器 profile 和第三方扩展快照，只做必要的 BOM 归一，不对内容做无依据的“自动修复”。

### Metadata
- Source: user_feedback
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\shared\runtime_storage.py, E:\work\project-manager\workhome\projects\ai-manga-factory\shared\quark_pan_sync.py, E:\work\project-manager\workhome\projects\ai-manga-factory\docs\夸克网盘业务产物同步.md
- Tags: encoding, utf8, file-hygiene

---

## [LRN-20260326-022] best_practice

**Logged**: 2026-03-26T21:20:00+08:00
**Priority**: high
**Status**: promoted
**Area**: remote-delivery

### Summary
业务产物同步到夸克网盘时，必须按 `项目 -> 能力 -> 适配包 -> job` 的层级上传，同时把适配包最新报告单独放在 `适配包汇总` 下，不能把整块 runtime 或测试材料直接丢到网盘根目录。

### Details
这次已经把夸克网盘接入到 `sync_runtime_storage.py` 和统一启动器里，并明确了上传范围：只上传交付视频、脚本、分镜、音频计划、QA 报告、结果摘要和 pack 级 latest 报告，不上传前端 smoke 文档、浏览器截图、临时日志和 provider 测试视频。这样网盘目录既适合归档，也适合按 job 和 pack 追溯。

### Suggested Action
后续默认使用：
`AI-Manga-Factory/业务产物/<project>/<capability>/<pack>/job_xxxx/...`
以及：
`AI-Manga-Factory/适配包汇总/<pack>/reports/...`

### Metadata
- Source: implementation
- Related Files: shared/quark_pan_sync.py, scripts/sync_runtime_storage.py, docs/夸克网盘业务产物同步.md
- Tags: quark-pan, delivery, remote-sync, artifact-structure
- Pattern-Key: remote-sync.quark_pan_use_project_capability_pack_job_hierarchy

### Resolution
- **Resolved**: 2026-03-26T21:20:00+08:00
- **Notes**: 已支持 `--dry-run`，可先验证网盘层级再真实上传。

## [LRN-20260326-020] best_practice

**Logged**: 2026-03-26T11:30:00+08:00
**Priority**: high
**Status**: promoted
**Area**: manga-video

### Summary
漫剧 smoke test 默认以 60 秒为最小测试单元，章节视频按章节内容实际可支撑的时长出片，不再为了凑时长重复分镜、循环画面或复用同一段视频片段。

### Details
这次排查发现，旧链路为了把测试片凑到较长时长，会重复分镜和循环采样出来的视频帧，导致视频内容密度虚高，也误伤了对剧本、分镜和视频模型效果的判断。当前修复后，章节时长可以通过 `target_duration_seconds` 显式传入，前端 smoke test 默认填 60 秒；如果章节实际内容不足，则按内容收口，不强行拉长。

### Suggested Action
后续默认遵循：
1. 分镜生成提示词、分镜重排、最终 QA 都要检查重复镜头和循环视频问题。
2. smoke test 的默认时长使用 60 秒，只有用户显式指定时才覆盖。
3. 章节第 01 章能支撑多少秒就输出多少秒，不再为了凑时长补重复画面。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, scripts/run_frontend_real_media_smoke.mjs, backend/schemas.py, backend/adaptation_packs.py, backend/main.py
- Tags: manga, storyboard, smoke-test, duration, qa
- Pattern-Key: manga.smoke_test_use_60s_without_repetition

### Resolution
- **Resolved**: 2026-03-26T11:30:00+08:00
- **Notes**: 默认 smoke test 时长已改为 60 秒，视频帧拉伸逻辑已去掉循环取模。
---

## [LRN-20260326-021] best_practice

**Logged**: 2026-03-26T11:35:00+08:00
**Priority**: high
**Status**: promoted
**Area**: verification-output

### Summary
浏览器截图、smoke 报告、provider 测试视频和临时验证日志不再落到 `ai-manga-factory` 业务项目目录，统一外置到 `workhome/management/ai-manga-factory/verification/`。

### Details
这次已经把项目内历史的 `data/*.png`、`data/*.mp4`、`data/*.log` 和 `data/frontend-smoke/` 迁出，并修改 smoke 脚本与 provider 测试脚本的默认输出路径。这样业务仓库只保留运行必需的数据与交付产物，验证材料统一放到项目外部管理目录。

### Suggested Action
后续新增任何测试或浏览器验收脚本时，默认把输出目录设计在：
`E:\work\project-manager\workhome\management\ai-manga-factory\verification\`
必要时再通过环境变量或 CLI 参数覆盖。

### Metadata
- Source: implementation
- Related Files: scripts/run_frontend_real_media_smoke.mjs, scripts/test_video.py, data/README.md, .gitignore
- Tags: verification, outputs, repository-hygiene, testing
- Pattern-Key: verification.outputs_live_outside_business_project

### Resolution
- **Resolved**: 2026-03-26T11:35:00+08:00
- **Notes**: 历史测试截图和 smoke 报告已迁出，脚本默认输出路径已改到 management 目录。

## [LRN-20260326-002] best_practice

**Logged**: 2026-03-26T01:19:00+08:00
**Priority**: high
**Status**: resolved
**Area**: runtime-recovery

### Summary
进程内后台任务模型下，服务重启后必须自动收敛遗留 `running` 任务，否则监控和控制台状态会长期失真。

### Details
这次为重启新代码，`job_32` 与 `job_33` 都留下了历史 `running` 状态。虽然产物目录已经部分生成，但从产品视角看，它们已经不是“正在执行”的有效任务，而是需要用户决定是否重跑的中断任务。把这种状态在启动时自动标记为 `failed`，比长期挂着 `running` 更真实，也更利于前端筛选和批量复跑。

### Suggested Action
在仍使用进程内后台任务时，后端启动流程默认先执行一次 orphaned job reconciliation；后续如果升级到 durable queue，再移除这层兜底。

### Metadata
- Source: implementation
- Related Files: backend/executor.py, backend/main.py
- Tags: recovery, jobs, runtime, monitoring
- Pattern-Key: backend.should_reconcile_orphaned_running_jobs_on_start

### Resolution
- **Resolved**: 2026-03-26T01:19:00+08:00
- **Notes**: 后端启动后当前 `jobs/summary` 已恢复 `running: 0`。

---

## [LRN-20260325-007] best_practice

**Logged**: 2026-03-25T21:42:00+08:00
**Priority**: high
**Status**: resolved
**Area**: smoke-test

### Summary
`ai-manga-factory` 的真图真视频最小前端 smoke test 基线应固定为 `dgyx_ch1_20 + 1-1 + scene_count=2 + use_real_images=true`，并以 `job_27` 作为当前参考样本。

### Details
这次从真实前端入口 `/?page=actions` 成功创建并完成了 `job_27`。结果表明，该组合既足够小，可以作为回归入口；又覆盖真实图片生成、视频分段、预览视频、交付视频、结果沉淀和自动校验。最终产物为 `真图数量 5，输出视频数量 4`，校验 `PASS 27/27`。

### Suggested Action
后续凡是要做“真图真视频链路是否可用”的快速验收，都优先走这一组参数，而不是整包全量运行；默认检查 `result_summary.md`、`validation_report.md`、`preview/preview.mp4`、`delivery/final_cut.mp4`。

### Metadata
- Source: implementation
- Related Files: scripts/run_frontend_real_media_smoke.mjs, C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory\artifacts\job_27
- Tags: smoke-test, real-media, frontend, manga, qa
- Pattern-Key: qa.real_media_smoke_should_use_dgyx_1_1_scene2_true_images

### Resolution
- **Resolved**: 2026-03-25T21:42:00+08:00
- **Notes**: `job_27` 已完成并通过 `PASS 27/27`。

---

## [LRN-20260325-008] best_practice

**Logged**: 2026-03-25T21:43:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend-bootstrap

### Summary
控制台首页或操作页的主流程数据加载不能和辅助面板绑死在同一个 `Promise.all`；否则辅助接口偶发失败就会把核心操作页拖成空状态。

### Details
这次真实 smoke test 中，`loadDashboard()` 因 `/artifacts-index` 和 `/jobs/summary` 未就绪而整体 rejected，`packs` 没有写入状态，页面上的“适配包”下拉框直接为空。说明对业务控制台来说，主流程数据和统计/证据面板必须分层加载。

### Suggested Action
后续控制台初始化默认分两层：
- 核心层：`capabilities / projects / jobs / adaptation-packs`
- 辅助层：`artifacts-index / jobs-summary / latest-result / provider-usage / model-stage-plan`
辅助层失败时只降级对应面板，不阻断任务创建、适配包运行和任务查看。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, data/frontend-smoke/smoke-failure.json
- Tags: bootstrap, resilience, frontend, dashboard
- Pattern-Key: ui.dashboard_bootstrap_should_degrade_optional_panels

### Resolution
- **Resolved**: 2026-03-25T21:43:00+08:00
- **Notes**: 本次问题已留档，待下一轮按此规则重构 `loadDashboard()`。

## [LRN-20260325-006] best_practice

**Logged**: 2026-03-25T01:35:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend-navigation

### Summary
业务控制台一旦同时承担操作、任务监控和证据阅读，就不应继续停留在“单页锚点导航”；应改成按功能分页面，并给产物统一的页面内预览入口。
### Details
这次用户明确指出左侧导航没有真正起作用，而且点击任务产物后会直接落到裸 `md/json` 文件。说明问题不在单个样式，而在信息架构：操作区、任务区、证据区和产物阅读本来就是不同任务上下文，继续堆在一个滚动页里只会放大错位和认知切换成本。更稳的方案是保留同一套数据拉取，但用 `?page=` 切成功能页，再把任务产物统一导向 Artifact Viewer，由页面内决定渲染 markdown/json/image/video/html。
### Suggested Action
后续凡是为业务控制台增加“结果入口”时，默认不要再直接把用户送去裸文件地址，而是先进入统一预览页；左侧导航也默认对应真实页面，而不是同页锚点。
### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css, backend/main.py
- Tags: navigation, artifact-viewer, frontend, backend, ux
- Pattern-Key: ui.dashboard_should_use_real_pages_and_artifact_viewer

### Resolution
- **Resolved**: 2026-03-25T01:35:00+08:00
- **Notes**: 已实现 `?page=` 页面切换和 Artifact Viewer，浏览器直接打开 `result_summary.md` 会落到控制台预览页。
---

## [LRN-20260325-005] best_practice

**Logged**: 2026-03-25T01:15:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: frontend-visual-system

### Summary
外部设计趋势参考不应直接翻译成“换皮”，而应先抽成适用于业务控制台的四类规则：主舞台层级、轻玻璃深度、状态感知卡片、可降级动效。
### Details
这次参考设计趋势页后，真正适合 `ai-manga-factory` 的不是照搬营销站式排版，而是把其有效信号提炼为：首屏必须同时承载当前焦点和关键数字；卡片要通过柔和渐变、边框和阴影建立层次；页面要根据运行状态给出自适应提示；交互动效必须有 `prefers-reduced-motion` 兜底。这样既能保留业务可读性，也能让控制台脱离“纯表单后台”的观感。
### Suggested Action
后续凡是参考外部视觉站点做控制台升级，先把灵感拆成“信息结构 / 视觉深度 / 状态表达 / 动效约束”四项，再决定是否改组件；不要先改颜色和阴影，最后才发现信息层级没有变化。
### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css
- Tags: design-system, dashboard, motion, accessibility, frontend
- Pattern-Key: ui.dashboard_should_translate_trends_into_operational_rules

### Resolution
- **Resolved**: 2026-03-25T01:15:00+08:00
- **Notes**: 已把趋势页里的主舞台、玻璃感、状态卡片和动效约束落到首页控制台。
---

## [LRN-20260325-004] best_practice

**Logged**: 2026-03-25T01:25:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend-layout

### Summary
仪表盘外层栅格列数必须和直接子节点一致，同时要显式放开 `#root` 与文本换行；否则页面会看起来“没有铺满”，并伴随侧栏挤压和文字溢出。
### Details
这次新版控制台出现的大面积右侧空白，不是内容不够，而是 `dashboard-shell` 定义了 3 列，但根层实际只有侧栏和主内容 2 个直接子节点，导致主内容被放进第二列，第三列整列空置。与此同时，根节点没有显式设置 `width: 100%`，侧栏又过窄，最终叠加成“页面缩在左边、文本被挤爆”的观感。修复方式是把外层栅格改成“侧栏 + 主内容”两列、显式给 `#root` 和主容器放宽、再给卡片正文和链接加 `overflow-wrap:anywhere`。
### Suggested Action
后续凡是做仪表盘重构，先检查“外层 grid 列数是否匹配直接子节点数量”，再检查 `#root/body` 是否显式铺满，以及窄列中的文案是否已经做换行约束；不要把这三项留到视觉验收阶段再排查。
### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css
- Tags: layout, grid, width, overflow, frontend
- Pattern-Key: ui.dashboard_root_grid_must_match_direct_children

### Resolution
- **Resolved**: 2026-03-25T01:25:00+08:00
- **Notes**: 已修复外层 grid 结构、`#root` 宽度和文本换行，浏览器截图确认页面已铺满。
---

## [LRN-20260325-003] best_practice

**Logged**: 2026-03-25T00:35:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: frontend-dashboard

### Summary
业务控制台升级时，应该先把页面结构提升为“导航 / 操作筛选 / 主监控证据”的仪表盘，而不是继续堆叠等权面板。

### Details
`ai-manga-factory` 之前虽然已经具备任务、适配包、证据和模型信息，但整体仍然偏文档流排列。重构为三栏仪表盘后，左侧负责导航，中间负责操作和筛选，右侧负责监控、证据和模型概览，用户在首屏同时能看到“我要做什么”和“当前发生了什么”。

### Suggested Action
后续凡是控制台级页面升级，优先先做信息架构重排，再补局部卡片和视觉细节；让操作入口和运行态判断同时处于首屏主视野。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css
- Tags: dashboard, layout, frontend, ux
- Pattern-Key: ui.dashboard_should_split_navigation_controls_and_monitoring

### Resolution
- **Resolved**: 2026-03-25T00:35:00+08:00
- **Notes**: 已重构为三栏仪表盘布局，并保留原有业务操作能力。

---

## [LRN-20260325-002] best_practice

**Logged**: 2026-03-25T00:14:00+08:00
**Priority**: high
**Status**: resolved
**Area**: monitoring-ui

### Summary
统一任务监控不能只靠能力和状态筛选，`job` API 还应直接返回 `project_name`，并支持关键词搜索，才能覆盖 `manga / finance / pack` 混合场景。

### Details
此前控制台已经能按能力和状态过滤，但 `job` 响应只给 `project_id`，前端无法直接按项目名、source title、target 或 pack name 做统一搜索。对 `ai-manga-factory` 这种多能力混跑项目来说，操作入口最终会回到“我想找某个项目、某个 source、某个 target 的那批任务”。因此更稳的基线是：后端把项目归属直接打到 job API，前端再基于 `project_name + context + summary + input` 做关键词搜索。

### Suggested Action
后续凡是控制台承担跨能力任务排查的职责，默认让 API 提供足够的归属字段，不要把项目名解析留给前端二次关联；前端列表至少支持能力、状态、关键词三类筛选，并可持久化到 URL。

### Metadata
- Source: implementation
- Related Files: backend/schemas.py, backend/storage.py, web/src/App.tsx, web/src/types.ts
- Tags: jobs, search, monitoring, api, frontend, backend
- Pattern-Key: jobs.api_should_include_project_name_for_cross_capability_search

### Resolution
- **Resolved**: 2026-03-25T00:14:00+08:00
- **Notes**: 最近任务已支持按项目名、source、target、pack 和 summary 关键词搜索，且与 URL 同步。

---

## [LRN-20260325-001] best_practice

**Logged**: 2026-03-25T00:10:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: monitoring-ui

### Summary
运行监控面板除了能力筛选，还应提供任务状态筛选，并与 URL 参数联动，方便快速切到 `running` 或 `failed` 视角排查。

### Details
`ai-manga-factory` 的最近任务已经支持能力维度过滤，但在 `manga` 长任务、`finance` 快任务混跑时，用户实际更常见的问题是“只看正在跑的”和“只看失败的”。如果没有状态筛选，只能靠人工扫卡片状态。把 `jobStatus` 也同步到地址栏后，监控链接本身就能表达更精确的排查上下文。

### Suggested Action
后续凡是用于任务监控的列表，默认同时支持业务维度和状态维度筛选；URL 至少应支持 `?capability=` 与 `?jobStatus=` 两类参数，便于刷新恢复和直接分享。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, README.md
- Tags: monitoring, jobs, filters, url-state, frontend
- Pattern-Key: ui.job_monitor_should_support_capability_and_status_filters

### Resolution
- **Resolved**: 2026-03-25T00:10:00+08:00
- **Notes**: 最近任务已支持 `all/running/completed/failed` 状态筛选，并持久化到 URL 与 localStorage。

---

## [LRN-20260324-009] best_practice

**Logged**: 2026-03-24T22:38:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: monitoring-ui

### Summary
任务监控类筛选条件不应只存在于临时组件状态里，至少要支持 URL 参数恢复，并用本地存储做兜底。

### Details
`ai-manga-factory` 的“最近任务”已经有能力筛选，但如果刷新页面就回到默认视图，PMO 之外的业务使用者在复查 `manga` 或 `finance` 任务时仍然要重复切换。把筛选状态同步到 `?capability=` 后，控制台链接本身就能表达当前视角；再用 localStorage 兜底，则即使用户直接打开根地址，也能回到上次关注的能力。

### Suggested Action
后续凡是控制台里的高频筛选条件，默认优先做成“URL 可表达、localStorage 可恢复、无效值自动回退”的模式，保证刷新、分享和二次进入都不丢上下文。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx
- Tags: url-state, localStorage, monitoring, frontend
- Pattern-Key: ui.dashboard_filters_should_persist_in_url_and_local_storage

### Resolution
- **Resolved**: 2026-03-24T22:38:00+08:00
- **Notes**: 最近任务能力筛选已支持 `?capability=` 分享和刷新恢复。

---

## [LRN-20260324-008] best_practice

**Logged**: 2026-03-24T22:25:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: monitoring-ui

### Summary
“最近任务”默认应优先展示运行中的任务，并提供按能力筛选入口，避免 `manga` 长任务和 `finance` 快任务混在一起时失去监控价值。

### Details
当前控制台已经能展示 active step、details 和关键产物，但如果列表仍只按更新时间平铺，实际运行中的任务会被刚完成的一批快任务冲下去。对 `ai-manga-factory` 这类混合型业务来说，用户最先要看的不是“谁最后写入了数据库”，而是“现在哪些任务还在跑、我当前关心哪一类能力”。因此最近任务区域要同时解决两个问题：运行中任务置顶、能力维度过滤。

### Suggested Action
后续凡是承担运行监控职责的任务面板，默认都优先排序 `running` 任务，并提供最轻量的能力筛选控件；筛选应该只影响展示，不改变底层任务数据和结果沉淀。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css
- Tags: monitoring, jobs, filtering, frontend, runtime
- Pattern-Key: ui.recent_jobs_should_prioritize_running_and_filter_by_capability

### Resolution
- **Resolved**: 2026-03-24T22:25:00+08:00
- **Notes**: 已给最近任务面板补 `running` 置顶排序和能力筛选 chips，前端构建通过。

---

## [LRN-20260324-007] best_practice

**Logged**: 2026-03-24T21:35:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: execution-efficiency

### Summary
业务控制台应直接提供“最近任务复跑”入口，优先复用原任务的 `project_id + capability_id + input` 创建新 job，而不是让用户手动重新填表。

### Details
当前 `ai-manga-factory` 已经有较完整的任务展示、产物入口和 smoke test 能力，但缺少“快速重来一次”的业务入口。对 `finance` 分析和 `manga` 小范围验路来说，用户最常见的动作不是重新设计参数，而是基于上一条任务再跑一次。把复跑能力接到现有 `/jobs` 计划链上后，新 job 可以继承原任务输入和项目归属，同时保持新的 job id、独立产物和完整审计链路。

### Suggested Action
后续凡是业务任务控制台，都优先补“复跑最近任务”能力。实现时不要直接复用旧 job 记录本身，而是重新走一次 `plan_job -> create_job -> execute`，保证工作流状态、产物目录和结果沉淀都是新的。

### Metadata
- Source: implementation
- Related Files: backend/main.py, web/src/App.tsx, web/src/styles.css
- Tags: jobs, retry, frontend, backend, execution
- Pattern-Key: jobs.retry_should_clone_input_but_create_fresh_job

### Resolution
- **Resolved**: 2026-03-24T21:35:00+08:00
- **Notes**: 已新增 `POST /jobs/{job_id}/retry`，并实测从 `finance #23` 复跑生成 `job_26`。

---

## [LRN-20260324-006] best_practice

**Logged**: 2026-03-24T20:15:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: monitoring-ui

### Summary
控制台的任务列表不能只显示最终摘要，至少要直接暴露 active step、step details 和关键产物入口，否则用户仍然需要翻 API 或文件系统判断任务状态。

### Details
前面虽然已经补了长任务进度回写，但如果“最近任务”面板只显示一句 summary，使用者仍然看不到当前卡在哪一步，也点不到最关键的结果文件。把任务卡片升级成监控视图后，控制台本身就能回答三个问题：现在在跑哪一步、为什么还没结束、可以先看哪些结果。

### Suggested Action
后续凡是展示运行中任务的界面，默认都至少渲染：任务上下文、active step、step details、关键产物链接。不要把这些信息藏到原始 JSON 或日志里。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, web/src/styles.css
- Tags: monitoring, frontend, jobs, runtime
- Pattern-Key: ui.job_cards_should_surface_active_step_and_artifacts

### Resolution
- **Resolved**: 2026-03-24T20:15:00+08:00
- **Notes**: `最近任务` 已升级为运行监控视图，并保留浏览器截图验证。

---

## [LRN-20260324-005] best_practice

**Logged**: 2026-03-24T20:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: smoke-test

### Summary
适配包控制台必须提供“单章或小范围 smoke test”入口，否则浏览器验收会被迫触发整包长任务，既昂贵又难定位问题。

### Details
这次新版主控台最初只有整包/分批按钮，没有章节范围控制。用 Agent Browser 做真实验收时，哪怕只是想验证提交链路和进度回写，也会被迫起一个 20 章长任务。补上 `开始章节` / `结束章节` 后，可以直接用 `1-1 / scene_count=2 / 占位图` 做低成本验证，并且真实跑出 `job_25`、`PASS 27/27` 和最新结果指针更新。

### Suggested Action
后续凡是面向验收或排障的运行入口，默认都保留最小执行粒度开关，例如章节范围、样本数量或 dry-run 选项。先让控制台能低成本验路，再去跑整包。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, data/agent-browser-pack-job25-complete.png
- Tags: smoke-test, frontend, manga, qa, browser
- Pattern-Key: ui.pack_controls_should_support_small_scope_smoke_tests

### Resolution
- **Resolved**: 2026-03-24T20:05:00+08:00
- **Notes**: 已补 `开始章节/结束章节`，并用 Agent Browser 跑通 `job_25` 单章 smoke test。

---

## [LRN-20260324-004] best_practice

**Logged**: 2026-03-24T04:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: long-running-jobs

### Summary
长任务的控制台验证不能只看“提交成功”和最终成败，还必须校验运行中进度是否能被前端感知，否则使用者会把正在产出的任务误判成卡死。

### Details
这次用 Agent Browser 提交 `dgyx_ch1_20 / 整包占位图` 后，`job_24` 实际已经持续生成到至少第 6 章的章节产物，但数据库 workflow 仍停在第一步 `research/running`。也就是说，提交链路没问题，真正缺的是执行过程中的进度回写。这种“后端在跑、前端看不见”的状态会直接破坏运行判断质量。

### Suggested Action
后续凡是长链路任务，默认同时验证三件事：提交是否成功、产物是否持续增长、workflow/summary 是否回写当前阶段。执行框架应提供统一进度回调，不要让每个模块各自发明状态写法。

### Metadata
- Source: implementation
- Related Files: backend/executor.py, modules/base.py, modules/manga/chapter_factory.py, data/agent-browser-pack-job24-running.png
- Tags: progress, workflow, long-running, frontend, runtime
- Pattern-Key: jobs.long_running_tasks_must_report_runtime_progress

### Resolution
- **Resolved**: 2026-03-24T04:05:00+08:00
- **Notes**: 已给执行上下文补 `report_progress`，`manga` 长任务后续会回写阶段与章节进度；本轮未重启旧进程，避免打断 `job_24`。

---

## [LRN-20260324-003] best_practice

**Logged**: 2026-03-24T03:55:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: frontend-qa

### Summary
前后端分离或控制台迁移后，不能只靠 `npm run build` 和 API 烟测判断可用，必须补一条真实浏览器驱动的低成本端到端任务链路。

### Details
这次 `ai-manga-factory` 的新版主控台在构建和接口层都通过了，但用 Agent Browser 真实提交 `finance` 任务后，才暴露出 `path_hint` 约定不一致导致自动校验误判的问题。这个问题不会在 `TestClient` 的只读接口验证里出现，只有通过真实页面做“选能力 -> 填表 -> 提交 -> 读结果”才会暴露。修复后再次用浏览器提交 `job_23`，结果变为 `PASS 3/3`，说明这类迁移必须保留浏览器级门禁。

### Suggested Action
后续凡是改动控制台、表单提交流程、结果入口或管理概览，默认都做三层验证：构建通过、API 烟测通过、浏览器跑一条低成本真实任务。优先选择不会触发高成本生产链路的能力做验收。

### Metadata
- Source: implementation
- Related Files: web/src/App.tsx, modules/finance/service.py, shared/result_depository.py, data/agent-browser-finance-job23.png
- Tags: frontend, browser, qa, validation, codex
- Pattern-Key: qa.frontend_changes_require_real_browser_low_cost_e2e

### Resolution
- **Resolved**: 2026-03-24T03:55:00+08:00
- **Notes**: 已用 Agent Browser 完成两次 `finance` 提交验证，修复后 `job_23` 自动校验为 `PASS 3/3`。

---

## [LRN-20260324-002] best_practice

**Logged**: 2026-03-24T03:40:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: architecture

### Summary
对于长期运行的业务项目，项目自身应直接暴露统一控制台，而不是把业务执行态割裂到多个入口。

### Details
这次对 `ai-manga-factory` 做前后端分离工程化时，发现真正影响长期协作效率的，不只是旧版单文件前端难维护，还包括任务执行、结果查看和控制入口分散。补上独立 `web/` 前端工程后，项目控制台可以集中展示业务执行状态和关键结果入口。

### Suggested Action
后续凡是会长期纳入 `multi-agent-framework-codex` 管理的业务项目，默认同步做三件事：前端工程独立、后端暴露管理概览接口、管理文档提供可点击访问入口。

### Metadata
- Source: implementation
- Related Files: backend/main.py, backend/management_overview.py, web/src/App.tsx, docs/前后端分离工程化架构.md
- Tags: architecture, frontend, backend, runtime, console
- Pattern-Key: engineering.expose_management_workspace_through_project_dashboard

### Resolution
- **Resolved**: 2026-03-24T03:40:00+08:00
- **Notes**: `ai-manga-factory` 已新增 `web/` 前端工程，新控制台已可直接读取任务、适配包结果和关键运行状态。

---

## [LRN-20260320-001] best_practice

**Logged**: 2026-03-20T01:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: storage

### Summary
AI 漫剧工厂的 `data/` 不能长期既当仓库静态数据目录，又当运行时产物目录；应拆成“项目内 reference + 独立运行时数据区”。

### Details
随着章节工厂、真图真视频、原文会话、模型账本和 QA 结果增多，`artifacts/`、`platform.db`、`provider_usage/`、`source_sessions/` 这类数据会快速膨胀，并且不适合继续放在 Git 工作区里。更稳的基线是：项目内 `data/reference/` 只保留静态参考数据；运行时数据根目录改为可配置，并优先放到 `OneDrive/CodexRuntime/ai-manga-factory` 这种同步目录。对正式远端存储，再额外接 `aliyun_oss` 这类对象存储，而不是把所有写入直接绑死到仓库目录。

### Suggested Action
后续新增运行时文件时，默认都经由 `backend.config.DATA_DIR` 这一层落到独立运行时目录；静态参考数据统一放 `REFERENCE_DATA_DIR`。如果需要远端存储，优先走“同步盘目录模式”或 `aliyun_oss` 脚本化同步，不要在业务层散落自定义网盘写路径。

### Metadata
- Source: implementation
- Related Files: backend/config.py, shared/runtime_storage.py, scripts/migrate_runtime_data.py, scripts/sync_runtime_storage.py, docs/运行时数据区与云存储.md
- Tags: storage, runtime, onedrive, oss, configuration
- Pattern-Key: storage.split_runtime_data_from_repo_reference

### Resolution
- **Resolved**: 2026-03-20T01:20:00+08:00
- **Notes**: 已把运行时数据根目录改成可配置，并默认落到 OneDrive；同时补了 OSS 同步脚本和迁移脚本。

---

## [LRN-20260319-028] best_practice

**Logged**: 2026-03-20T00:15:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: workflow

### Summary
当 Codex 周额度紧张时，最省成本的推进方式是把重复执行交给本地脚本，只把代码改造、复杂排障和流程设计留给 Codex。

### Details
当前 AI 漫剧工厂已经有较完整的本地入口：`start.bat`/`start.sh` 启动后端，`run_adaptation_pack.py` 跑整包，`validate_job_output.py` 做结果复验。为减少 Codex 消耗，又补了 `run_pack.bat`，让 Windows 下也能直接完成“跑包 + 校验”。这意味着后续在额度不足时，不需要停止项目，而是切换到“本地批处理 + Codex 批量处理高价值问题”的模式。

### Suggested Action
后续额度紧张时，优先让用户本地执行：原文导入、摘要生成、整包生产、自动校验；仅在需要改代码、定位复杂失败、补 QA 规则或升级模型路由时再调用 Codex。

### Metadata
- Source: implementation
- Related Files: run_pack.bat, docs/Codex额度节省执行方案.md, docs/AI漫剧工厂操作手册.md
- Tags: codex, quota, local-first, workflow
- Pattern-Key: quota.low_codex_budget_use_local_batch_scripts_first

### Resolution
- **Resolved**: 2026-03-20T00:15:00+08:00
- **Notes**: 已补 `run_pack.bat` 和《Codex额度节省执行方案》文档，Windows 下可直接本地跑包并自动复验。

---

## [LRN-20260319-027] best_practice

**Logged**: 2026-03-19T23:45:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: video-qa

### Summary
章节最终 QA 不能只校验“文件是否存在”，必须额外校验 `video_plan.json`、真实图生视频命中情况、成片运动性和时长是否贴合分镜计划。

### Details
这次排查发现章节成片主链原先只是“关键帧静态图 + 旁白 + 本地合成”，而最终 QA 仍然只检查预览视频、交付视频、分镜 Excel 和旁白文件是否存在，导致“成片看起来还在动，但本质没有正确使用图生视频链”也能通过。现在章节工厂已改成先生成 `video_plan.json`，再按关键帧驱动 Ark 图生视频资产，并在最终 QA 里验证真实视频资产数量、真实/回退镜头数、运动评分、预览/交付时长一致性和分镜目标时长。

### Suggested Action
后续凡是调整章节视频链、切换视频模型或修改镜头装配策略时，都要同步检查这四类门禁是否仍成立：`video_plan` 完整、真实视频资产可追溯、运动评分不过低、成片时长不明显偏离分镜计划。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, shared/providers/ark.py, shared/result_depository.py
- Tags: qa, video, i2v, validation
- Pattern-Key: qa.chapter_video_must_validate_real_i2v_and_motion

### Resolution
- **Resolved**: 2026-03-19T23:45:00+08:00
- **Notes**: 已把章节视频链改成关键帧驱动的图生视频优先，并把 `video_plan.json`、运动评分和真实视频命中率接入最终 QA。

---

## [LRN-20260317-001] best_practice

**Logged**: 2026-03-17T06:30:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: backend

### Summary
Management run sync must not trust shared report files unless they match the current job id.

### Details
The management sync flow originally read `projects/dgyx_ch1_20/reports/stage_report.md` and
`validation_report.md` directly. That caused stale summaries when a new job was created through
the API preset path, because background job execution did not rewrite those shared reports.
The correct pattern is to prefer the current job's own summary and artifact directory, and only
reuse shared reports when they explicitly reference the same job id.

### Suggested Action
Keep job-id matching whenever management or QA views consume shared report files. Fall back to
job-scoped artifacts or recomputed checks when the report is stale.

### Metadata
- Source: simplify-and-harden
- Related Files: backend/run_management.py, shared/result_depository.py, backend/main.py, frontend/index.html
- Tags: management, sync, reports, qa
- Pattern-Key: harden.report_job_alignment

### Resolution
- **Resolved**: 2026-03-24T04:15:00+08:00
- **Notes**: 已补 `latest_result_pointer.json` 结构化指针、`/adaptation-packs/{pack_name}/latest-result` 接口，并把前端“最近一次结果”入口切到显式 `job_id` 绑定的 job 级证据；共享 `latest_result.md` / `latest_validation.md` 仅保留为便捷副本。

---

## [LRN-20260319-025] best_practice

**Logged**: 2026-03-19T16:20:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: frontend

### Summary
阶段模型分配应以 `data/reference/model_stage_plan.json` 作为单一事实源，由后端 `GET /model-stage-plan` 暴露给首页，而不是在前端脚本里重复维护阶段与模型映射。

### Details
这次为首页补“阶段模型分配”面板时，如果直接在 `frontend/index.html` 里写死阶段名称、默认模型和降级链，后续一旦 `ark.py`、`generate_chapter_briefs.py` 或文档里的模型策略调整，首页展示就会与实际生产链脱节。改成由 `backend/main.py` 读取 `data/reference/model_stage_plan.json` 并通过统一接口返回后，首页只负责渲染，阶段规划、文档和展示可以围绕同一份结构化数据同步演进。

### Suggested Action
后续凡是新增阶段、调整默认模型、修改降级规则或加入 `Seedance 2.0` 升级条件，优先更新 `data/reference/model_stage_plan.json` 和对应文档，再让前端继续读取 `/model-stage-plan`，不要回到页面硬编码模式。

### Metadata
- Source: implementation
- Related Files: backend/main.py, backend/schemas.py, frontend/index.html, data/reference/model_stage_plan.json
- Tags: frontend, backend, model-routing, single-source-of-truth
- Pattern-Key: frontend.render_stage_plan_from_structured_source

### Resolution
- **Resolved**: 2026-03-19T16:20:00+08:00
- **Notes**: 首页阶段模型分配面板已改为走 `/model-stage-plan`，接口与前端脚本烟测通过。
---
## [LRN-20260319-026] best_practice

**Logged**: 2026-03-19T22:10:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: startup

### Summary
The project root should always provide zero-config startup wrappers so users do not need to remember the long PowerShell command with execution policy flags.

### Details
The backend already had `run_backend.ps1`, but the actual startup command still required users to `cd` into the project and invoke `powershell -ExecutionPolicy Bypass -File .\\run_backend.ps1`. That is fragile in daily use and easy to mistype. The stable baseline is to keep simple root launchers that reuse the shared venv, honor `AI_MANGA_FACTORY_PYTHON`, and default to the backend entrypoint. On Windows this should be `start.bat`; in bash environments this should be `start.sh`.

### Suggested Action
Keep `start.bat` and `start.sh` as the primary documented startup entrypoints. If Python path resolution or host/port defaults change later, update the wrappers and docs together instead of pushing users back to long raw commands.

### Metadata
- Source: implementation
- Related Files: start.bat, start.sh, run_backend.ps1, docs/AI漫剧工厂操作手册.md, docs/ai-manga-factory-使用说明.md
- Tags: startup, wrappers, developer-experience
- Pattern-Key: startup.prefer_short_root_wrappers_over_long_shell_commands

### Resolution
- **Resolved**: 2026-03-19T22:10:00+08:00
- **Notes**: Added `start.bat` and repurposed `start.sh` to start the backend by default while keeping pack-run compatibility.

## [LRN-20260319-024] user_preference

**Logged**: 2026-03-19T17:48:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: provider-routing

### Summary
用户已开通的方舟模型都可以作为备选，不应只保留一个或两个 fallback。

### Details
用户明确补充“我开的模型都可以做为备选”。这意味着在 AI 漫剧工厂里，模型路由策略应保持“主模型优先 + 所有已开通模型按优先级依次兜底”，而不是狭义地只留单个备用模型。只要模型已开通且已写入配置，就应保留 `enabled=true`，由 `priority` 决定尝试顺序。

### Suggested Action
后续调整火山方舟模型基线时，默认保留所有已开通模型为备选，并把主模型、次优模型和兼容别名统一写进 `model_budget_config.json`。

### Metadata
- Source: user_feedback
- Related Files: data/provider_usage/model_budget_config.json, shared/providers/ark.py
- Tags: ark, fallback, routing, user-preference
- Pattern-Key: provider.keep_all_opened_ark_models_as_backups

### Resolution
- **Resolved**: 2026-03-19T17:48:00+08:00
- **Notes**: 文本链已补齐 `doubao-seed-1.6` 作为额外备选，现有配置中的已开通模型全部保持启用。
---
## [LRN-20260319-023] best_practice

**Logged**: 2026-03-19T17:35:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: provider-routing

### Summary
切换火山方舟模型基线时，要按“公开可用的 API 模型”而不是体验中心最强模型来定生产默认值。

### Details
这次模型基线更新里，文本和图片都可以安全切到 `Doubao Seed 2.0` 与 `Seedream 5.0` 的公开 API 模型；但官方资料里 `Seedance 2.0` 仍主要处于体验中心阶段，不应直接作为 AI 漫剧工厂的视频生产默认值。生产默认视频模型继续使用 `doubao-seedance-1-5-pro-251215`，并保留 `doubao-seedance-1-0-pro-250528` 为后备，才能保证现有任务链条稳定。

### Suggested Action
后续遇到“控制台里能体验但 API 文档尚未正式开放”的模型，先写入候选清单，不直接升为生产默认值；只有官方 API 文档或正式可调用记录确认后再切。

### Metadata
- Source: implementation
- Related Files: shared/providers/ark.py, shared/providers/model_usage.py, data/provider_usage/model_budget_config.json
- Tags: volcengine, api-availability, routing, production-baseline
- Pattern-Key: provider.only_promote_models_with_public_api_availability

### Resolution
- **Resolved**: 2026-03-19T17:35:00+08:00
- **Notes**: 默认文本已切到 `doubao-seed-2-0-pro-260215`，默认图片已切到 `doubao-seedream-5-0-260128`，默认视频保持 `doubao-seedance-1-5-pro-251215`。
---
## [LRN-20260319-022] user_preference

**Logged**: 2026-03-19T17:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: provider-routing

### Summary
AI 漫剧工厂后续默认优先使用指定的 Ark 模型顺序，不再把别名模型放在主位。

### Details
用户明确指定优先模型为：文本 `doubao-seed-1-6-251015`，图片 `doubao-seedream-4-5-251128`，视频 `doubao-seedance-1-5-pro-251215`，视频后备 `doubao-seedance-1-0-pro-250528`。这意味着默认配置和 Provider 默认值都要与该顺序保持一致，不能让 `Doubao-Seedream-4.5` 或 `Doubao-Seedance-1.5-pro` 这类别名继续占主位。

### Suggested Action
后续新增或重建 `model_budget_config.json` 时，保持：
- text: `doubao-seed-1-6-251015`
- image: `doubao-seedream-4-5-251128`
- video: `doubao-seedance-1-5-pro-251215`
- backup video: `doubao-seedance-1-0-pro-250528`

### Metadata
- Source: user_feedback
- Related Files: shared/providers/ark.py, shared/providers/model_usage.py, data/provider_usage/model_budget_config.json
- Tags: ark, model-priority, defaults
- Pattern-Key: provider.prefer_user_pinned_ark_models

### Resolution
- **Resolved**: 2026-03-19T17:05:00+08:00
- **Notes**: 默认值、回退顺序和预算配置已全部对齐用户指定模型。
---
## [LRN-20260319-020] best_practice

**Logged**: 2026-03-19T16:40:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: provider-routing

### Summary
Ark 文本、图片、视频调用不应只依赖单次异常回退，应该统一接入可持久化的用量账本，在接近预算阈值时提前切到后备模型，并把额度类错误写入封禁窗口。

### Details
这次《斗破苍穹》长链路里，Ark 文模型因为 `AccountOverdueError` 在中后段掉回 fallback 分镜，说明“等错误发生再兜底”对整包生产不够稳。后续基线改为在 `data/provider_usage/` 里持久化预算配置和用量账本，由 `shared/providers/ark.py` 在调用前先看预计用量，再决定是否切换模型；调用后回写成功失败次数、估算 tokens、最近错误和最近切换事件。这样前端也能直接展示当前模型和预警状态。

### Suggested Action
后续所有 Ark 接入都统一经过 `ModelUsageManager`，不要在业务层私自写模型切换逻辑；预算阈值统一维护在 `data/provider_usage/model_budget_config.json`。

### Metadata
- Source: implementation
- Related Files: shared/providers/model_usage.py, shared/providers/ark.py, backend/main.py, frontend/index.html, data/provider_usage/model_budget_config.json
- Tags: ark, quota, routing, monitoring, persistence
- Pattern-Key: provider.route_models_with_persistent_budget_ledger

### Resolution
- **Resolved**: 2026-03-19T16:40:00+08:00
- **Notes**: 首页已提供 `GET /provider-usage` 的可视化监控，ArkProvider 已支持额度阈值切换和额度错误临时封禁。
---

## [LRN-20260319-021] best_practice

**Logged**: 2026-03-19T16:40:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: verification

### Summary
验证模型用量账本时，应该使用临时配置文件和临时账本文件做烟测，避免把模拟额度错误和模拟切换事件污染正式运行数据。

### Details
这次在验证“接近上限 -> 自动切换 -> 额度错误封禁 -> 再次切换”链路时，如果直接使用正式 `usage_ledger.json`，首页会把烟测写入当成真实用量展示。后续验证改成 `tempfile.TemporaryDirectory()` 下的临时账本路径，接口连通性再单独用正式应用做只读验证。

### Suggested Action
后续凡是对 provider usage 账本做烟测，一律使用临时 `config_path` 和 `ledger_path`，跑完后保持正式 `usage_ledger.json` 为空或仅保留真实运行数据。

### Metadata
- Source: implementation
- Related Files: shared/providers/model_usage.py, data/provider_usage/usage_ledger.json
- Tags: verification, ledger, smoke-test, isolation
- Pattern-Key: verification.use_temp_ledgers_for_provider_usage_smoke_tests

### Resolution
- **Resolved**: 2026-03-19T16:40:00+08:00
- **Notes**: 已把正式 `usage_ledger.json` 重置为空账本，只保留真实运行时数据。
---

## [LRN-20260319-017] best_practice

**Logged**: 2026-03-19T20:12:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: storyboard

### Summary
模型分镜里的“关键帧优先级”字段不能假设一定是数字，章节工厂应兼容“高/中/低”和中文数字，避免无意义回退模板。

### Details
这次第 13 章和第 19 章的单章真图返工虽然最终通过，但 provider notes 显示模型返回了“高”“中”之类的优先级文本，旧逻辑直接 `int()` 转换会报错并回退到模板分镜。这个问题不影响最终可用性，但会降低模型分镜命中率。

### Suggested Action
后续所有结构化模型输出里，只要字段存在枚举化或自然语言表达的可能，都优先做容错归一化，而不是假设模型永远严格输出数字。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_13/result_summary.md, data/artifacts/job_14/result_summary.md
- Tags: storyboard, parsing, robustness, model-output
- Pattern-Key: normalize_model_priority_fields_before_casting

### Resolution
- **Resolved**: 2026-03-19T20:12:00+08:00
- **Notes**: 关键帧优先级已支持数字、高中低和中文数字容错解析。

---

## [LRN-20260319-014] best_practice

**Logged**: 2026-03-19T20:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: qa

### Summary
章节返工不能只把 QA 的 `issues` 回灌给分镜生成，`blockers` 也必须进入返工闭环，并且要有确定性的自动补强规则兜底。

### Details
这次《斗破苍穹》全量真图任务 `job_12` 在最终 QA 门禁处失败，原因不是 API 生成失败，而是第 13 章和第 19 章的节奏、名台词和世界规则没有被真正修正。根因是返工只传了 `issues`，像“名台词没有进入章节分镜”这样的 `blockers` 没有进入下一轮，同时分镜生成没有做确定性的名台词落点、规则落点和节奏重平衡。

### Suggested Action
后续所有章节级 QA 返工都保持“双通道回灌”：`issues + blockers` 一起传回生成层，并对名台词、世界规则、时长带和首尾钩子保留自动补强逻辑，避免同一章无效重复三轮。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_12/chapters/chapter_13/qa/qa_snapshot.json, data/artifacts/job_12/chapters/chapter_19/qa/qa_snapshot.json
- Tags: qa, retry, blockers, storyboard
- Pattern-Key: qa.feed_blockers_back_into_storyboard_revision

### Resolution
- **Resolved**: 2026-03-19T20:05:00+08:00
- **Notes**: 返工闭环已改为 `issues + blockers` 同步回灌，且分镜生成加入名台词、世界规则、节奏和钩子补强。

---

## [LRN-20260319-015] best_practice

**Logged**: 2026-03-19T20:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: production

### Summary
章节工厂需要可复用的“整包收尾器”，用于在少量章节返工后重建总预览、总交付、总 QA 和沉淀文件，而不是默认整包重跑。

### Details
`job_12` 里 20 章都已生成，但只有第 13 章和第 19 章未通过 QA。如果没有收尾器，就只能再花近一小时全量重跑。新增 `finalize_chapter_job.py` 后，可以用返工章节替换原章节目录，再重建总视频、章节索引、QA 总览、manifest、summary 和 validation，把“局部返工 -> 总包重建”变成正式能力。

### Suggested Action
后续章节工厂类项目一律保留“章节替换 + 整包重建”能力，把章节作为最小返工单元、整包作为可重建聚合层。

### Metadata
- Source: implementation
- Related Files: scripts/finalize_chapter_job.py, data/artifacts/job_12/result_summary.md, data/artifacts/job_12/validation_report.md
- Tags: production, resume, finalize, partial-rerun
- Pattern-Key: production.rebuild_whole_package_from_reworked_chapters

### Resolution
- **Resolved**: 2026-03-19T20:05:00+08:00
- **Notes**: `job_12` 已通过替换 `job_13` 和 `job_14` 的修复章节重建为完整 PASS 总包。

---

## [LRN-20260319-016] best_practice

**Logged**: 2026-03-19T20:05:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: validation

### Summary
章节工厂的校验器必须按真实章节号校验，而不是假设所有子任务都从 `chapter_01` 开始编号。

### Details
这次用 `job_13` 和 `job_14` 验证单章返工时，章节实际目录分别是 `chapter_13` 和 `chapter_19`，但校验器仍按 `1..chapter_count` 去找 `chapter_01`，导致真实通过的返工任务被误报为 FAIL。这会直接破坏“局部返工”的可信度。

### Suggested Action
后续校验逻辑优先从 `chapter_briefs` 或 `chapter_start/chapter_end` 解析真实章节号，只有缺失时才回退到 `1..episode_count`。

### Metadata
- Source: implementation
- Related Files: shared/result_depository.py, data/artifacts/job_13/validation_report.md, data/artifacts/job_14/validation_report.md
- Tags: validation, chapter-numbering, partial-rerun
- Pattern-Key: validation.use_real_chapter_numbers_for_subset_jobs

### Resolution
- **Resolved**: 2026-03-19T20:05:00+08:00
- **Notes**: 校验器已按真实章节号解析，`job_13` 与 `job_14` 重新校验后均为 PASS。

---

## [LRN-20260319-010] best_practice

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: adaptation-quality

### Summary
AI 漫剧工厂的全部智能体必须共享同一套改编质量宪法，把还原度、叙事节奏、制作水平和改编合理性作为统一硬约束，而不是分散写在单个提示词里。

### Details
这次需求明确要求把 4 个硬指标和精品加分项写入全部智能体，并允许为了 QA 达标反复返工。实践结果表明，单独在运行脚本或单个 agent 中补提示词不够稳定，必须把约束沉淀为项目级常量和统一文档，然后在 screenwriter、director、image-generator、video-generator、qa-engineer 等全部角色里引用同一来源，才能避免角色之间标准不一致。

### Suggested Action
继续把新增智能体和后续流程节点都绑定到统一质量宪法，任何新能力接入时优先复用共享约束，而不是再写一套局部标准。

### Metadata
- Source: implementation
- Related Files: shared/adaptation_quality.py, agents/QUALITY_CONSTITUTION.md, agents/qa-engineer/SOUL.md
- Tags: quality, agents, constitution, adaptation
- Pattern-Key: quality.share_one_constitution_across_all_agents

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: 质量约束已经沉淀到 `shared/adaptation_quality.py` 与 `agents/QUALITY_CONSTITUTION.md`，并同步写入各角色 SOUL。

---

## [LRN-20260319-011] best_practice

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: storyboard

### Summary
外部分镜表不应只作为一次性参考文件，必须先转成可持久化的 JSON 和节奏 profile，再驱动章节级分镜模板与视频时长控制。

### Details
用户提供的 `storyboard_ep1_timing_adjusted.xlsx` 对章节节奏优化是高价值输入。如果只靠人工目测参考，后续扩展到多章节、多项目时无法复用，也无法稳定校准时长。把表格内容导入为 `storyboard_reference_ep1.json` 和 `storyboard_profile.json` 后，章节工厂可以直接使用统一节奏分组、目标时长和镜头分配策略生成每章分镜与视频。

### Suggested Action
后续新增任何分镜模板、导演表或镜头规划表时，都优先先做结构化导入，再交给生产流程消费，不直接依赖原始 Excel。

### Metadata
- Source: implementation
- Related Files: scripts/import_storyboard_reference.py, shared/storyboard_reference.py, data/reference/storyboard_profile.json
- Tags: storyboard, excel, persistence, pacing
- Pattern-Key: storyboard.persist_excel_reference_before_generation

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: Excel 分镜参考已导入并持久化，章节工厂默认按该 profile 生成章节分镜和视频时长。

---

## [LRN-20260319-012] best_practice

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: production

### Summary
小说转漫剧的生产基线必须是“章节工厂”而不是“整包一次性产物”：每一章都要独立产出脚本、分镜、音频、预览视频、交付视频和 QA 结果。

### Details
用户明确要求“每一章，所要产生物都要有”“都要输出视频”。原先只有整包级产物时，不利于逐章返工、局部重跑和章节级交付。改为章节工厂后，每章都会落地自己的 storyboard、audio、preview、delivery、qa 目录，同时整包层继续保留汇总视频和总清单，既满足交付，也方便后续扩展到批量重做和多轮 QA。

### Suggested Action
后续所有新模块、校验器和前端页面都应以章节包为最小交付单元设计，整包层只做索引和聚合。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, modules/manga/service.py, shared/result_depository.py
- Tags: chapter-factory, deliverables, video, qa
- Pattern-Key: production.chapter_is_the_smallest_delivery_unit

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: `job_11` 已验证 20/20 章节都生成独立视频和完整章节交付包。

---

## [LRN-20260319-013] best_practice

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: qa

### Summary
QA 在漫剧流程里必须是硬门禁，不能用“文件都生成了”替代“质量已通过”；不达标就直接让任务失败并返工。

### Details
这次在章节工厂烟测时，发现如果只看文件存在性，任务会显示 completed，但章节 QA 实际并未通过。对于强调还原度、节奏和改编合理性的项目，这种“软 QA”会把低质量产物误判成可交付结果。把 QA 改成硬门禁后，只要任一章节未通过，整包任务就会抛错并终止，迫使流程回到返工路径。

### Suggested Action
后续增强 QA 时，保持“门禁优先”原则：允许增加更细的评分维度，但不要把失败降级为仅报告不阻塞。

### Metadata
- Source: implementation
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_11/qa_overview.md
- Tags: qa, gating, iteration, delivery
- Pattern-Key: qa.fail_the_job_when_any_chapter_fails

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: 章节工厂已在运行时强制 QA 门禁，`job_11` 的 20 章全部通过后才标记完成。

---

## [LRN-20260317-002] best_practice

**Logged**: 2026-03-17T23:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: backend

### Summary
Management run job matching must return no jobs when the configured project name does not exist yet.

### Details
The orchestration flow creates runs before the first project-specific job may exist in the platform
database. The previous `_matching_jobs()` logic filtered by capability first and only applied
project filtering if matching project ids existed. That meant a brand-new run with
`project_name = dgyx-orchestrator-smoke` would incorrectly inherit every existing `manga` job from
other projects, causing batch orchestration to think chapters were already covered.

### Suggested Action
When a run declares a `project_name`, treat the absence of matching project ids as an empty result
set rather than a wildcard match.

### Metadata
- Source: error
- Related Files: backend/run_management.py
- Tags: management, orchestration, project-filtering
- Pattern-Key: harden.run_project_job_matching

### Resolution
- **Resolved**: 2026-03-17T23:20:00+08:00
- **Notes**: `_matching_jobs()` now returns `[]` when a run has a project name but that project does not yet exist.

---

## [LRN-20260318-001] correction

**Logged**: 2026-03-18T00:20:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: backend

### Summary
New orchestration and management code should include concise comments for non-obvious control flow.

### Details
The user explicitly asked for code comments to be added as part of normal implementation. This is
especially important in this repository because management automation, retry chains, and batch
orchestration contain stateful logic that operators may need to inspect quickly.

### Suggested Action
When adding or changing orchestration, retry, or management synchronization code, include short
comments ahead of non-obvious branches, derived state, or cross-file workflow assumptions.

### Metadata
- Source: user_feedback
- Related Files: backend/run_management.py, backend/executor.py, frontend/index.html
- Tags: comments, maintainability, workflow
- Pattern-Key: maintain.comment_non_obvious_logic

---

## [LRN-20260318-002] best_practice

**Logged**: 2026-03-18T00:56:39.7768589+08:00  
**Priority**: high  
**Status**: pending  
**Area**: backend

### Summary
Management sync should generate human-facing management artifacts from the same run state snapshot.

### Details
This project became much easier to operate once `sync_management_run()` stopped updating only role
status and started emitting the decision pack and delivery release bundle from the same derived
state. That keeps API payloads, markdown handoff files, CLI output, and the dashboard aligned,
instead of forcing operators to infer management conclusions from scattered raw artifacts.

### Suggested Action
Keep management summaries, delivery handoff files, and UI state derived from the same sync pass.
When adding a new management-facing view, generate it from the run snapshot rather than from
separate ad-hoc file reads.

### Metadata
- Source: simplify-and-harden
- Related Files: backend/run_management.py, backend/main.py, scripts/manage_run.py, frontend/index.html
- Tags: sync, release, runtime
- Pattern-Key: unify.run_snapshot_outputs

---

## [LRN-20260319-007] user_preference

**Logged**: 2026-03-19T00:00:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: source-ingestion

### Summary
起点中文网在当前用户环境下使用微信扫码登录，应优先按扫码回跳后的浏览器会话做原文接入。

### Details
用户明确补充“起点中文网我是通过微信扫描登录的”。这意味着原文接入流程不能默认依赖账号密码表单自动化，而应优先复用用户手动扫码后的 Edge/Chromium 会话，等待回跳到目录页后再导出 HTML、Cookie 和 storage state。

### Suggested Action
保留“附着现有浏览器会话”的抓取链，默认支持微信扫码登录后的会话导出，并在起点相关文档中把扫码登录列为首选路径。

### Metadata
- Source: user_feedback
- Related Files: scripts/capture_manual_browser_session.py, scripts/playwright_source_capture.py, docs/Playwright正版原文抓取.md
- Tags: qidian, wechat-login, browser-session, source-ingestion
- Pattern-Key: source.weixin_qr_login_attach

---

## [LRN-20260318-003] best_practice

**Logged**: 2026-03-18T00:56:39.7768589+08:00  
**Priority**: high  
**Status**: pending  
**Area**: backend

### Summary
Multi-agent project management is easier to scale when management assets and business execution are physically separated.

### Details
This repository became clearer after `workhome` was split into management assets (`pm/`,
templates, run workspaces, release docs) and business code (`backend/`, `frontend/`, `modules/`,
`scripts/`, project inputs, generated artifacts). That separation made initialization, cleanup,
run cloning, and role-based coordination much simpler, especially when management runs need to be
tracked independently from chapter generation jobs.

### Suggested Action
Preserve the split between management state and business execution. New automation, templates,
checklists, and role workspaces should stay under `pm/`, while execution code and generated content
should stay in business directories.

### Metadata
- Source: simplify-and-harden
- Related Files: E:/work/project-manager/workhome/management/ai-manga-factory/README.md, E:/work/project-manager/workhome/management/ai-manga-factory/project-manager/README.md, backend/run_management.py
- Tags: structure, management, workflow
- Pattern-Key: separate.management_from_execution

---

## [LRN-20260318-004] correction

**Logged**: 2026-03-18T00:56:39.7768589+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: docs

### Summary
Operator-facing project documentation in this repository should default to Chinese.

### Details
The user explicitly corrected the root project documentation language. For this project, the main
operator and management-facing documents are expected to be Chinese so the platform can be run and
reviewed directly without translation overhead.

### Suggested Action
Default new root-level operational documents, PM summaries, and project management docs to Chinese
unless a file is explicitly meant for external or bilingual audiences.

### Metadata
- Source: user_feedback
- Related Files: README.md, E:/work/project-manager/workhome/management/ai-manga-factory/MEMORY.md, E:/work/project-manager/workhome/management/ai-manga-factory/PROJECT_SUMMARY.md
- Tags: docs, language, operations
- Pattern-Key: docs.default_chinese_operator_docs

---

## [LRN-20260318-005] correction

**Logged**: 2026-03-18T01:02:03.6664077+08:00  
**Priority**: high  
**Status**: pending  
**Area**: docs

### Summary
以后与用户的对话、项目文档、以及代码中的新增注释都默认使用中文。

### Details
用户明确要求后续沟通语言、项目内文档语言、以及代码注释语言统一为中文。这一约束不影响
代码标识符、接口路径、模型名、命令行参数等本身需要保持原样的技术字段，但所有面向人的
解释性内容都应默认使用中文。

### Suggested Action
从当前对话开始，默认使用中文回复；新增或修改的项目文档使用中文；新增或修改代码时，
所有解释性注释使用中文，除非某段内容明确要求保留英文原文。

### Metadata
- Source: user_feedback
- Related Files: README.md, E:/work/project-manager/workhome/management/ai-manga-factory/MEMORY.md, .learnings/LEARNINGS.md
- Tags: 中文, 对话, 文档, 注释
- See Also: LRN-20260318-004
- Pattern-Key: language.default_chinese_everywhere

---

## [LRN-20260318-006] best_practice

**Logged**: 2026-03-18T11:20:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: docs

### Summary
项目基线不应携带 `.venv`，但所有入口文档必须明确写出环境初始化步骤。

### Details
这次清理把业务项目里的 `.venv` 从模板基线中移除了，避免仓库携带本机环境垃圾和大体积依赖。
同时也暴露出一个固定要求：凡是 `run_backend.ps1`、README、后端说明、业务使用说明这类入口文档，
都必须写清楚 `python -m venv .venv` 和 `pip install -r requirements.txt`，否则操作者会误以为项目可以
直接启动。

### Suggested Action
以后凡是清理或新建业务项目骨架，都默认不提交 `.venv`，并同步补齐环境初始化命令到入口文档。

### Metadata
- Source: refactor
- Related Files: README.md, docs/ai-manga-factory-使用说明.md, backend/README.md, run_backend.ps1
- Tags: environment, docs, baseline
- Pattern-Key: baseline.no_venv_but_docs_required

---

## [LRN-20260318-007] best_practice

**Logged**: 2026-03-18T11:40:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: infra

### Summary
这个工作区里的 AI 漫剧工厂更适合把虚拟环境放在工作区级目录，而不是项目目录内部。

### Details
用户明确要求“虚拟环境找一个更合理的地方”。对当前目录结构来说，把解释器放到
`E:\work\.venvs\ai-manga-factory` 更合理：项目目录继续保持干净，业务代码、运行数据和依赖环境
分离，后续做目录审查或复制项目骨架时也不会把本机环境误带进去。

### Suggested Action
默认使用 `E:\work\.venvs\ai-manga-factory` 作为 AI 漫剧工厂的虚拟环境位置；启动脚本、README、
使用说明和操作手册都应优先指向这个路径，同时允许通过 `AI_MANGA_FACTORY_PYTHON` 覆盖。

### Metadata
- Source: user_feedback
- Related Files: run_backend.ps1, README.md, docs/ai-manga-factory-使用说明.md, docs/AI漫剧工厂操作手册.md
- Tags: venv, environment, workspace
- Pattern-Key: infra.workspace_level_venv_for_ai_manga_factory

---

## [LRN-20260318-008] best_practice

**Logged**: 2026-03-18T15:20:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: adaptation

### Summary
要满足高还原度改编标准，章节摘要不能只靠标题驱动的模型常识生成，最终版必须接入原文章节文本或人工校对材料。

### Details
这次已经打通“模型生成剧情摘要 -> 真图 -> 真视频 -> 交付视频”的完整链路，并成功跑通了《斗破苍穹》整包。
但在只提供作品名、未提供原文章节文本时，模型虽然能生成可运行的章节摘要，却会在中后段出现时间线漂移和剧情跳跃，
难以满足“角色不崩、名场面保留、世界观一致、路人也能看懂”的高标准。因此，标题驱动版本只能作为首版草稿，
不能直接视为最终改编蓝本。

### Suggested Action
把当前模型摘要能力定位为“首版改编草稿生成器”；要进入正式制作，下一步必须支持原文章节输入、
官方剧情梗概输入或人工审校后的摘要回填。

### Metadata
- Source: implementation
- Related Files: scripts/generate_chapter_briefs.py, adaptations/dpcq_ch1_20/chapter_briefs.json, modules/manga/service.py
- Tags: adaptation, fidelity, outline, workflow
- Pattern-Key: adaptation.source_text_required_for_final_fidelity

---

## [LRN-20260318-009] best_practice

**Logged**: 2026-03-18T15:21:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: provider

### Summary
当前 Ark 额度足够支撑一轮《斗破苍穹》20 章真图真视频流程。

### Details
本轮《斗破苍穹》`dpcq_ch1_20` 真图整包任务 `job_5` 成功完成，结果沉淀显示：
- 真图数量：21
- 真视频数量：1
- 校验结果：PASS 31/31

这说明现有 Ark key 在当前时点至少足够支撑一轮完整的图片和视频生成，不需要因为额度问题提前降级。

### Suggested Action
后续如果继续跑多轮大批量真图任务，仍应在每轮结束后从 `result_summary.md` 和 `prompts.json` 检查真实生成数量，
及时识别额度下降或回退到占位图的情况。

### Metadata
- Source: implementation
- Related Files: data/artifacts/job_5/result_summary.md, data/artifacts/job_5/prompts.json
- Tags: ark, quota, real-images, verification
- Pattern-Key: provider.ark_quota_verified_for_one_full_run

---

## [LRN-20260318-010] best_practice

**Logged**: 2026-03-18T16:18:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: adaptation

### Summary
小说适配包的原文输入应统一沉淀到 `source/chapters` 与 `source_manifest.json`，让原文导入、摘要生成和人工校对共享同一套结构。

### Details
这次为 AI 漫剧工厂补原文驱动能力时，如果只做“临时抓取脚本”而不约定固定落盘结构，后续会再次出现导入脚本、摘要生成脚本和人工修订文件各用一套格式的问题。统一到 `source/chapters/chapter_0001.md` 加 `source_manifest.json` 后，单文件拆章、逐章目录导入、URL 清单采集和目录页采集都能复用同一条后续链路。

### Suggested Action
后续新的小说适配包默认创建 `source/` 目录；任何原文、官方梗概或人工整理稿都先沉淀到这套结构里，再进入模型摘要和视频生成流程。

### Metadata
- Source: implementation
- Related Files: scripts/collect_source_text.py, scripts/generate_chapter_briefs.py, shared/source_materials.py, scripts/create_adaptation_pack.py
- Tags: adaptation, source-text, pipeline, ingestion
- Pattern-Key: adaptation.standardize_source_material_layout

---

## [LRN-20260318-011] best_practice

**Logged**: 2026-03-18T16:42:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: integration

### Summary
对官方受保护阅读页，稳定做法不是假设匿名可抓，而是同时准备“认证抓取”和“浏览器保存 HTML 离线导入”两条链路。

### Details
这次验证起点官方页时，匿名请求拿到的是 202 + `probe.js` 校验壳，不是正文。这说明“只写 URL 抓取脚本”不足以支撑正式原文导入。把认证头、Cookie 文件和保存 HTML 的离线导入一起做进去之后，原文入口才能真正适配正版站点的现实限制。

### Suggested Action
后续涉及正版原文导入时，默认先创建 `request_headers.template.json` 与 `request_cookies.template.json`，同时保留 `source-dir` 导入 HTML 的回退路径。

### Metadata
- Source: implementation
- Related Files: scripts/collect_source_text.py, shared/source_materials.py, docs/小说原文导入工具.md
- Tags: source-text, official-site, cookies, html
- Pattern-Key: integration.support_authenticated_and_saved_html_ingestion

---

## [LRN-20260318-012] best_practice

**Logged**: 2026-03-18T17:02:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: docs

### Summary
外部能力调研结果应同时沉淀为机读注册表和人工可读报告，避免后续扩展时重复检索。

### Details
这次用户要求“搜索一下可以用的获取小说原文工具或者脚本，再输出一些结构化的数据给后面的流程用，并且这些数据做一下持久化”。如果只回一段文字说明，后续脚本无法直接消费，也无法作为长期底账。把结果同时落成 `data/reference/source_ingestion_registry.json` 和 `docs/原文获取工具调研.md` 之后，既方便脚本读取，也方便人工快速复核。

### Suggested Action
后续凡是涉及外部工具、库、平台选型的调研，默认至少沉淀一份机读 JSON 注册表；如果会被运营或开发直接查阅，再补一份中文报告。

### Metadata
- Source: implementation
- Related Files: data/reference/source_ingestion_registry.json, shared/source_tool_catalog.py, docs/原文获取工具调研.md
- Tags: tooling, registry, persistence, research
- Pattern-Key: docs.persist_external_tool_research_as_registry

---

## [LRN-20260319-001] best_practice

**Logged**: 2026-03-19T02:18:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: scripts

### Summary
给外部抓取脚本补能力时，应该先用本地 `file://` 样例页做最小闭环验证，再去碰真实站点。

### Details
这次为 `playwright_source_capture.py` 落地 Playwright 认证抓取时，先用本地两页 HTML 和 URL 清单打通了 `capture -> playwright_html -> collect_source_text`。这样很快就暴露出漏导入 `normalize_text` 的问题，避免把真实站点的登录、反爬和页面差异混进调试噪音里。

### Suggested Action
后续凡是新增浏览器抓取、正文提取或认证导出脚本，默认先准备最小本地 fixture 页面和清单，跑通本地闭环后再接真实站点。

### Metadata
- Source: implementation
- Related Files: scripts/playwright_source_capture.py, scripts/collect_source_text.py, adaptations/dpcq_ch1_20/reports/source_access_status.md
- Tags: playwright, fixtures, smoke-test, source-ingestion
- Pattern-Key: scripts.validate_source_capture_with_local_fixtures_first

---

## [LRN-20260319-002] best_practice

**Logged**: 2026-03-19T10:28:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: adaptation

### Summary
对正版阅读站点，保存目录页 HTML 后先自动生成 `source_urls.json`，比手工抄写章节链接稳定得多。

### Details
这次为《斗破苍穹》适配包补抓取入口时，额外实现并验证了 `build_source_url_manifest.py`，能从保存下来的目录页 HTML 自动识别章节号、拼接链接并回填到 `source_urls.json`。这一步把“准备 URL 清单”的手工工作压缩成了“保存一个目录页 HTML + 跑一次脚本”，明显更稳。

### Suggested Action
后续处理官方小说站点时，优先让用户保存目录页 HTML，再自动生成或合并 `source_urls.json`；只有目录页结构过于复杂时再手工编辑。

### Metadata
- Source: implementation
- Related Files: scripts/build_source_url_manifest.py, adaptations/dpcq_ch1_20/source/incoming/source_urls.json, docs/Playwright正版原文抓取.md
- Tags: toc, source-urls, automation, ingestion
- Pattern-Key: adaptation.prefer_toc_html_to_generate_source_url_manifest

---

## [LRN-20260319-003] best_practice

**Logged**: 2026-03-19T10:56:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: scripts

### Summary
把 Playwright 配置文件放在 `source/` 目录时，模板里的默认路径应优先写成相对 `source/` 的 `incoming/...`，避免在不同解析基准下重复拼路径。

### Details
这次给 `run_source_ingestion_pipeline.py` 做本地闭环时，`playwright_capture.template.json` 里的 `adaptations/<pack_name>/source/incoming/request_headers.json` 被按配置文件目录再次拼接，变成了 `.../source/adaptations/...`。虽然随后在 `resolve_path_option()` 里补了兼容逻辑，但从模板设计上直接写成 `incoming/request_headers.json`、`incoming/request_cookies.json`、`incoming/source_urls.json` 更稳，也更符合配置文件和目标文件共置的目录关系。

### Suggested Action
后续凡是放在 `source/` 下的抓取配置文件，默认使用相对 `source/` 的 `incoming/...` 路径；脚本侧再保留对项目根相对路径的兜底兼容。

### Metadata
- Source: implementation
- Related Files: shared/source_materials.py, scripts/playwright_source_capture.py, adaptations/dpcq_ch1_20/source/playwright_capture.template.json
- Tags: config, playwright, path-resolution, source-ingestion
- Pattern-Key: scripts.prefer_source_relative_paths_in_playwright_templates

---

## [LRN-20260319-004] best_practice

**Logged**: 2026-03-19T10:58:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: scripts

### Summary
Windows 下由包装脚本调用多个 Python 子进程时，应强制 `PYTHONIOENCODING=utf-8`，并在最终控制台输出前做编码兼容处理。

### Details
这次一键原文抓取流水线在真实失败分支里暴露出两个问题：子脚本输出可能按本地代码页返回，导致沉淀报告难读；而包装脚本在直接打印失败原因时，又可能被 `GBK` 控制台二次打断。给 `subprocess.run()` 注入 `PYTHONIOENCODING=utf-8`，再对最终错误文本做 `safe_console_text()` 兼容处理后，流水线失败也能稳定沉淀并正常退出。

### Suggested Action
后续新增“包装型” Python 入口时，默认给子进程注入 UTF-8 输出环境，并把终端打印视为单独的兼容层，而不是直接回显原始异常文本。

### Metadata
- Source: implementation
- Related Files: scripts/run_source_ingestion_pipeline.py
- Tags: windows, encoding, subprocess, wrapper
- Pattern-Key: scripts.force_utf8_for_python_wrapper_subprocesses

---

## [LRN-20260319-005] best_practice

**Logged**: 2026-03-19T11:35:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: integration

### Summary
对起点这类站点，不应把“真实浏览器自动化”误判成天然可过验证；即使不是裸 HTTP，请求也可能先落到腾讯滑块验证码。

### Details
这次改用 `agent-browser` 探测起点首页和《斗破苍穹》目录页，页面没有直接给出目录 DOM，而是稳定返回腾讯滑块验证码壳。说明“浏览器自动化”只能减少一部分静态反爬误判，但对更严格的 WAF 场景仍然需要人工接管、真实已登录资料，或站点允许的验证流程。

### Suggested Action
后续凡是把“真实浏览器自动化”当作原文入口时，都要保留人工验证码/登录接管预案，并把 WAF 壳 HTML、截图和浏览器状态一起沉淀到项目目录，避免重复试错。

### Metadata
- Source: implementation
- Related Files: adaptations/dpcq_ch1_20/reports/agent_browser_qidian_probe.md, adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.html
- Tags: qidian, waf, captcha, browser-automation
- Pattern-Key: integration.real_browser_automation_still_needs_human_takeover_on_qidian

---

## [LRN-20260319-006] best_practice

**Logged**: 2026-03-19T11:37:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: integration

### Summary
如果要复用系统 Edge 默认资料导出登录态，应先确认所有 Edge 窗口都已关闭；否则 Playwright 持久化上下文很可能直接失败。

### Details
这次尝试直接复用 `C:\\Users\\Administrator\\AppData\\Local\\Microsoft\\Edge\\User Data` 启动 Playwright 持久化上下文时，Edge 进程启动后立即退出。结合本机还有大量运行中的 Edge 进程，可以确认这是“资料目录正在被占用”的高概率场景，而不是 Playwright 配置本身有问题。

### Suggested Action
后续若要借用系统浏览器资料，应先让用户关闭对应浏览器，再尝试持久化上下文导出状态；如果浏览器必须保持打开，则优先改用人工接管一次后导出状态。

### Metadata
- Source: implementation
- Related Files: adaptations/dpcq_ch1_20/reports/agent_browser_qidian_probe.md
- Tags: edge, profile, playwright, persistent-context
- Pattern-Key: integration.close_system_edge_before_persistent_profile_export

---

## [LRN-20260319-007] user_preference

**Logged**: 2026-03-19T12:05:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: source-ingestion

### Summary
起点中文网在当前用户环境下使用微信扫码登录，应优先按扫码回跳后的浏览器会话做原文接入。

### Details
用户明确补充“起点中文网我是通过微信扫描登录的”。这意味着原文接入流程不能默认依赖账号密码表单自动化，而应优先复用用户手动扫码后的 Edge/Chromium 会话，等待回跳到目录页后再导出 HTML、Cookie 和 storage state。

### Suggested Action
保留“附着现有浏览器会话”的抓取链，默认支持微信扫码登录后的会话导出，并在起点相关文档中把扫码登录列为首选路径。

### Metadata
- Source: user_feedback
- Related Files: scripts/capture_manual_browser_session.py, scripts/playwright_source_capture.py, docs/Playwright正版原文抓取.md
- Tags: qidian, wechat-login, browser-session, source-ingestion
- Pattern-Key: source.weixin_qr_login_attach

---

## [LRN-20260319-008] best_practice

**Logged**: 2026-03-19T12:35:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: source-ingestion

### Summary
起点正文批量抓取时，复用用户已扫码登录的真实浏览器会话并通过 CDP 顺序抓章，比把 storage state 迁移到新 Playwright 上下文稳定得多。

### Details
这次《斗破苍穹》前 20 章验证里，`playwright_source_capture.py` 复用导出的 storage state 与 Cookie 去新建 Playwright 浏览器时，只有第 1 章抓到真正文，后续页面迅速退化成“尝试太多次 / 验证码”壳页。改为附着用户刚刚微信扫码通过的 Edge 会话，使用 `capture_cdp_chapters.py` 在同一真实浏览器上下文里顺序打开章节页后，20/20 正文稳定落盘。

### Suggested Action
对起点这类强 WAF 阅读站，优先走“人工扫码登录 -> CDP 附着目录页 -> 同会话顺序抓章节 -> 导入 source/chapters”的路径；只有在确认复制会话不会退化时才尝试迁移到新 Playwright 上下文。

### Metadata
- Source: implementation
- Related Files: scripts/capture_manual_browser_session.py, scripts/capture_cdp_chapters.py, adaptations/dpcq_ch1_20/reports/source_access_status.md
- Tags: qidian, cdp, authenticated-browser, anti-bot
- Pattern-Key: source.prefer_cdp_capture_over_rehydrated_storage_state_for_qidian

---

## [LRN-20260319-009] best_practice

**Logged**: 2026-03-19T13:05:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: media-generation

### Summary
Ark 视频生成遇到 `Invalid content.text` 时，不应立刻降级为假视频，先对 prompt 做压缩清洗并重试一次。

### Details
《斗破苍穹》`job_6` 的真视频创建在 Ark 端返回 `Invalid content.text`，导致系统回退到本地拼接视频，`真视频数量` 变成 0。补上视频 prompt 候选与清洗重试逻辑后，再跑 `job_7`，同一条生产链成功生成了 `真视频数量 1` 的正式结果。

### Suggested Action
后续所有 Ark 视频调用保留“原 prompt -> 清洗压缩 prompt”两级候选；只有两次都失败时再回退到本地拼接视频，并把失败原因写入 `provider_notes`。

### Metadata
- Source: implementation
- Related Files: shared/providers/ark.py, data/artifacts/job_6/result_summary.md, data/artifacts/job_7/result_summary.md
- Tags: ark, video, retry, prompt-sanitization
- Pattern-Key: media.retry_ark_video_with_sanitized_prompt_before_fallback

---

## [LRN-20260319-018] best_practice

**Logged**: 2026-03-19T15:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: brief-generation

### Summary
对接正版原文章节时，`generate_chapter_briefs.py` 不应继续沿用默认 `batch-size=3` 和较大的章节截断长度；长章节更稳的基线是 `batch-size=1 + source-max-chars=1800`。

### Details
这次《斗破苍穹》`dpcq_ch21_40` 已接入起点正版前 20 章原文后，直接执行默认批量摘要生成命令时，进程在 Ark 文本调用阶段长时间无输出，外层命令在约 244 秒后超时，`chapter_briefs.json` 仍保持占位内容。改为先单章探针，再用 `--batch-size 1 --source-max-chars 1800 --force` 全量重跑后，20 章摘要稳定生成完成。说明在“逐章原文驱动 + 长章节正文”场景下，减小单次输入规模比堆超时更可靠。

### Suggested Action
后续凡是用正版长篇原文批量重生成摘要，默认使用：
`python scripts/generate_chapter_briefs.py --pack-name <pack> --batch-size 1 --source-max-chars 1800 --force`
只有在验证通过后再尝试放大 batch。

### Metadata
- Source: implementation
- Related Files: scripts/generate_chapter_briefs.py, adaptations/dpcq_ch21_40/chapter_briefs.json, adaptations/dpcq_ch21_40/reports/brief_generation_report.md
- Tags: ark, brief-generation, source-driven, batching
- Pattern-Key: brief-generation.use_batch_size_1_for_long_source_chapters

### Resolution
- **Resolved**: 2026-03-19T15:20:00+08:00
- **Notes**: `dpcq_ch21_40` 已按 `batch-size=1` 稳定生成 20 章摘要并完成后续整包生产。

---

## [LRN-20260319-019] best_practice

**Logged**: 2026-03-19T15:20:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: source-ingestion

### Summary
起点正版目录页一旦被真实浏览器会话捕获并沉淀下来，就应优先复用同一份目录页 HTML 继续扩章，而不是每次重新登录和重抓目录。

### Details
这次把《斗破苍穹》从 `1-20` 章扩到 `21-40` 章时，没有重新扫码登录，而是直接复用 `dpcq_ch1_20/source/incoming/qidian_catalog_live.html` 重新生成 `dpcq_ch21_40/source/incoming/source_urls.json`，随后沿用仍在线的 `http://127.0.0.1:9333` CDP 会话顺序抓取 21-40 章 HTML。结果 20/20 章节抓取成功，说明“目录页 HTML 持久化 + URL 清单重建”是扩章最省事且最稳的路径。

### Suggested Action
后续继续扩到 `41-60`、`61-80` 章时，优先复用已有目录页 HTML 和在线 CDP 会话，只在目录结构变化或会话失效时才重新抓取目录页。

### Metadata
- Source: implementation
- Related Files: adaptations/dpcq_ch1_20/source/incoming/qidian_catalog_live.html, adaptations/dpcq_ch21_40/source/incoming/source_urls.json, adaptations/dpcq_ch21_40/reports/manual_browser_capture_report.md
- Tags: qidian, cdp, source-ingestion, scaling
- Pattern-Key: source.reuse_catalog_html_when_extending_chapter_ranges

### Resolution
- **Resolved**: 2026-03-19T15:20:00+08:00
- **Notes**: `dpcq_ch21_40` 已复用前序目录页资产完成 URL 重建和 20 章正文抓取。

---
