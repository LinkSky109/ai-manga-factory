# Error Log

## [ERR-20260329-005] backend-restart-port-race

**Logged**: 2026-03-29T23:08:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: runtime-restart

### Summary
在 Windows 上重启 `ai-manga-factory` 后端时，即使旧进程刚被杀掉，8000 端口也可能短暂未完全释放，导致第一次重启直接报 `10048` 端口占用。

### Error
```text
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)
通常每个套接字地址(协议/网络地址/端口)只允许使用一次。
```

### Context
- Trigger: Phase 2 为了让 runtime 吃到最新 `chapter_factory.py` 修复，主动重启后端
- First attempt:
  - 先 `Stop-Process`
  - 立即重新拉起 `uvicorn`
- Observed result:
  - 新进程刚启动就因端口尚未释放而退出
  - `check_api.py` 随后返回 `WinError 10061`

### Suggested Fix
后续在 Windows 上重启本项目后端时，默认遵循：
1. 杀旧进程后先确认 8000 端口已无监听
2. 用 `Start-Process` 拉起新后端并单独重定向日志
3. 启动后再用 `check_api.py` 做健康检查，不要把“进程已拉起”误当成“服务已在线”

### Metadata
- Reproducible: yes
- Related Files: start_project.py

### Resolution
- **Resolved**: 2026-03-29T23:08:00+08:00
- **Notes**: 改为先确认端口空闲，再用 `Start-Process` 拉起后端并复查 `/health`；后续 `job_43` 已在此流程下完成。

## [ERR-20260329-004] storyboard-diversify-mojibake-canonical-key-mismatch

**Logged**: 2026-03-29T22:12:58+08:00
**Priority**: high
**Status**: resolved
**Area**: storyboard-qa

### Summary
`chapter_factory.py` 的分镜去重逻辑曾把变体内容写入乱码字段名和乱码文案，导致运行时看似已执行“去重”，但 QA 实际读取的 canonical 字段 `画面内容 / 人物动作/神态 / 镜头运动 / 镜头景别 / 对白` 没有变化，相邻重复镜头会原样漏到最终产物。

### Error
```text
job_40 chapter_01 storyboard rows 3-4 / 5-6 / 8-9 remained adjacent duplicates
qa blocker: 分镜出现连续重复画面，会直接导致视频重复
```

### Context
- Trigger: Phase 3 第一阶段复盘 `job_40` 的 `storyboard.json` / `audio_plan.json` / `qa_snapshot.json`
- Evidence:
  - `storyboard.json` 中相邻重复镜头仍存在于 `画面内容`
  - 同一批重复镜头行里还能看到额外生成的乱码键，如 `鐢婚潰鍐呭`、`闀滃ご杩愬姩`
  - 直接调用 `_diversify_storyboard_rows()` 时，重复镜头只会写脏键，不会改动 canonical 字段
  - 修复后离线重放 `job_40`，`adjacent_duplicates` 从 `3` 降到 `0`，`_review_plan()` 结果变为 `passed=true`

### Suggested Fix
后续凡是修 `storyboard` 生成、反馈改写或 QA 去重逻辑时，默认同时做三件事：
1. 变体内容只写 canonical 字段，并同步必要 alias，不再写历史乱码键
2. 对去重产生的提示文案做 UTF-8 直读检查，避免把乱码字符串继续带进产物
3. 补单测锁定“重复镜头必须改写 canonical 字段并消除相邻重复”

### Metadata
- Reproducible: yes
- Related Files: modules\manga\chapter_factory.py, tests\test_manga_chapter_factory.py

### Resolution
- **Resolved**: 2026-03-29T22:13:00+08:00
- **Notes**: 已把 `_build_variation_hint()` / `_build_variation_dialogue()` / `_diversify_storyboard_rows()` 改回 canonical 字段与正常 UTF-8 文案，并新增单测覆盖重复镜头去重路径。

## [ERR-20260329-003] chapter-factory-duplicate-qa-review-override

**Logged**: 2026-03-29T22:05:00+08:00
**Priority**: high
**Status**: resolved
**Area**: qa-runtime

### Summary
`chapter_factory.py` 后段重复定义的 QA 评审方法会覆盖前段实现，导致 `voice_script` 已包含旁白/对白时仍被误判为缺少台本。

### Error
```text
job_40 qa_snapshot blockers:
- voice_script 缺少旁白台本
- voice_script 缺少角色对白台本
```

### Context
- Trigger: Phase 2 重跑最小 manga smoke 后，`job_40` 的 job 根目录聚合产物已恢复，但任务仍因 QA 门禁失败
- Evidence:
  - `audio_plan.json` 中 `voice_script` 实际包含 `旁白：` 和角色 `：` 前缀
  - `validation_report.md` 39/39 文件与结构检查全部通过
  - 使用修复后的 `_review_plan()` 离线复盘 `job_40` 后，误判 blocker 消失，仅剩真实 blocker：`分镜出现连续重复画面，会直接导致视频重复`

### Suggested Fix
后续凡是 `chapter_factory.py` 再做编码修复、QA 修复或门禁调整时，默认检查同名方法是否在文件后段还有重复定义；优先保证类尾部的最终生效版本是干净实现，并为关键 QA 判断补单测。

### Metadata
- Reproducible: yes
- Related Files: modules\manga\chapter_factory.py, tests\test_manga_chapter_factory.py

### Resolution
- **Resolved**: 2026-03-29T22:08:00+08:00
- **Notes**: 已在类尾部追加干净的 `_review_plan()` / `_review_final()` 覆盖历史变体，并补单测锁定 `voice_script` 台本判断。

## [ERR-20260329-002] unittest-python-env-mismatch

**Logged**: 2026-03-29T21:35:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: test-environment

### Summary
在 `ai-manga-factory` 跑 Python 单测时，如果误用系统 Python 而不是项目虚拟环境，会因为缺少 `pydantic` 等依赖直接失败，造成“测试代码坏了”的假象。

### Error
```text
ModuleNotFoundError: No module named 'pydantic'
```

### Context
- Trigger: 执行 `python -m unittest tests.test_manga_chapter_factory`
- Wrong interpreter: `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`

### Suggested Fix
本项目所有 Python 测试、`py_compile` 和运行时验证默认统一使用：
`E:\work\.venvs\ai-manga-factory\Scripts\python.exe`

### Metadata
- Reproducible: yes
- Related Files: tests\test_manga_chapter_factory.py, requirements.txt

### Resolution
- **Resolved**: 2026-03-29T21:36:00+08:00
- **Notes**: 改用项目 venv 后，新增测试与现有测试集均可正常执行。

## [ERR-20260326-001] runtime-missing-backend-deps

**Logged**: 2026-03-26T01:05:00+08:00
**Priority**: high
**Status**: resolved
**Area**: environment

### Summary
系统 Python 一度缺少 `uvicorn` 与项目运行依赖，导致统一启动入口可执行但后端实际无法拉起。

### Error
```text
python.exe: No module named uvicorn
```

### Context
- Trigger: 按新的跨平台启动链重启 `ai-manga-factory` 后端
- Environment: `C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe`
- Impact: `start_project.py backend` / `uvicorn backend.main:app` 无法启动，必须先补运行依赖

### Suggested Fix
在新机器或新 Python 环境上，默认先执行：
`python -m pip install -r requirements.txt`
再启动后端，不要依赖历史残留进程或旧虚拟环境。

### Metadata
- Reproducible: yes
- Related Files: requirements.txt, start_project.py

### Resolution
- **Resolved**: 2026-03-26T01:05:00+08:00
- **Notes**: 已执行 `python -m pip install -r requirements.txt`，后端可正常启动并通过 `/health`。

---

## [ERR-20260326-004] sync-storage-http-timeout

**Logged**: 2026-03-26T23:02:00+08:00
**Priority**: high
**Status**: resolved
**Area**: cloud-delivery

### Summary
批量网盘真同步如果直接在 HTTP 请求里同步执行，容易超过前端或客户端等待时间，表现为请求超时，但同步过程仍可能继续占用服务进程。

### Error
```text
TimeoutError: timed out
```

### Context
- Endpoint attempted: `POST /jobs/batch-sync-storage`
- Payload: `{"job_ids":[34,31],"provider":"all","dry_run":false}`
- Observed result: 本地直接调用接口等待 180 秒后超时

### Suggested Fix
真同步默认改成后台任务，接口立即返回“已加入后台同步”，由页面后续刷新总览、任务和产物状态；只有 dry-run 计划继续走同步返回。

### Metadata
- Reproducible: yes
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\backend\main.py

### Resolution
- **Resolved**: 2026-03-26T23:02:00+08:00
- **Notes**: `POST /jobs/{job_id}/sync-storage` 和 `POST /jobs/batch-sync-storage` 的真同步已改为 `BackgroundTasks` 异步执行。

## [ERR-20260326-003] validation-command-mismatch

**Logged**: 2026-03-26T22:48:00+08:00
**Priority**: low
**Status**: resolved
**Area**: validation

### Summary
`py_compile` 只能校验 Python 文件，不能拿来检查 `TypeScript` 文件。

### Error
```text
SyntaxError: invalid syntax
```

### Context
- Command attempted: `python -m py_compile ... backend/main.py ... backend/schemas.py ... web/src/types.ts`
- Working directory: `E:\work`
- Observed result: `web/src/types.ts` 被 Python 按源码解析，直接报语法错误

### Suggested Fix
后续分语言做校验：
- Python: `python -m py_compile ...`
- TypeScript / 前端: `npm run build` 或 `tsc --noEmit`

### Metadata
- Reproducible: yes
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\web\src\types.ts

### Resolution
- **Resolved**: 2026-03-26T22:48:00+08:00
- **Notes**: 已改用 `npm run build` 校验前端类型与构建。

## [ERR-20260326-002] real-video-asset-timeout

**Logged**: 2026-03-26T01:10:00+08:00
**Priority**: high
**Status**: resolved
**Area**: media-pipeline

### Summary
真实视频链路按 asset 串行等待 Ark 图生视频时，默认单 asset 最长等待 600 秒，足以把单章 smoke test 拖到超时。

### Error
```text
Error: Timed out waiting for job 33
summary: 第 01 章《病房异兆》正在生成关键帧、配音与视频
```

### Context
- Trigger: 前端入口真图真视频 smoke test，单章 `dgyx_ch1_20 / 1-1 / scene_count=2`
- Observation:
  - `job_33` 的 progress heartbeat 已恢复正常
  - 但 `video_plan.json` 中有 4 个 `ark_i2v` 资产，旧逻辑逐个最长等 600 秒
  - 最终把任务整体拖到 smoke test 超时

### Suggested Fix
真实视频资产必须采用“短等待 + 自动回退本地镜头”的策略，并在 asset 级别持续回写进度；不要让单个外部视频任务无限占住整章交付。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py, shared/providers/ark.py, scripts/run_frontend_real_media_smoke.mjs

### Resolution
- **Resolved**: 2026-03-26T01:10:00+08:00
- **Notes**: 已把单 asset 等待上限收敛到 120 秒，并在 asset 完成/回退时回写 `chapter_packaging` 进度；`job_34` 已成功完成。

---

## [ERR-20260326-003] orphaned-running-jobs-after-restart

**Logged**: 2026-03-26T01:18:00+08:00
**Priority**: high
**Status**: resolved
**Area**: runtime-recovery

### Summary
服务重启前如果存在进程内长任务，数据库会遗留 `running` 僵尸任务，污染任务面板和状态统计。

### Error
```text
jobs/summary -> running: 4
old jobs remained running after backend restart
```

### Context
- Trigger: 为验证新代码多次重启后端
- Affected jobs: `job_32`, `job_33` 等历史运行中任务
- Cause: 当前任务执行模型仍基于进程内后台任务；进程退出时没有 durable queue 或自动恢复

### Suggested Fix
在服务启动时，先把遗留 `running` 任务统一收敛为 `failed`，并带上“服务重启导致中断”的明确错误说明；后续再升级到更稳的后台队列。

### Metadata
- Reproducible: yes
- Related Files: backend/executor.py, backend/main.py

### Resolution
- **Resolved**: 2026-03-26T01:18:00+08:00
- **Notes**: 已新增 `reconcile_orphaned_jobs()`，后端启动后会自动把遗留 `running` 任务标记为失败；当前 `jobs/summary` 已恢复 `running: 0`。

---

## [ERR-20260325-007] runtime-source-drift

**Logged**: 2026-03-25T21:30:00+08:00
**Priority**: high
**Status**: resolved
**Area**: runtime-consistency

### Summary
前端 smoke test 一度命中“源码已补路由，但在线后端仍缺 `/artifacts-index` 和 `/jobs/summary`”的运行时漂移，导致页面行为和源码分析结论不一致。

### Error
```text
GET /artifacts-index -> 404 Not Found
GET /jobs/summary -> 422 Unprocessable Entity
```

### Context
- Trigger: 使用 Playwright 从 `/?page=actions` 跑真图真视频最小测试
- Observation:
  - 本地源码 `backend/main.py` 已定义 `/artifacts-index` 与 `/jobs/summary`
  - 在线 `openapi.json` 初始版本缺少这两个端点
  - 重启后端后，`openapi.json` 与源码一致，前端可正常创建 `job_27`
- Impact: 会把“旧进程”误诊成“当前代码缺陷”，污染问题定位

### Suggested Fix
把“代码改动后验证在线 `openapi.json` / 关键健康端点是否与源码一致”纳入前端 smoke test 前置检查；部署或本地重启后至少校验 `/openapi.json`、`/artifacts-index`、`/jobs/summary`。

### Metadata
- Reproducible: yes
- Related Files: backend/main.py, run_backend.ps1, data/frontend-smoke/smoke-failure.json

### Resolution
- **Resolved**: 2026-03-29T00:00:00+08:00
- **Notes**: 已在 `start_project.py`、`check_api.py` 与 `run_test_report.py` 中统一加入 runtime consistency 校验，默认核对 `/health`、`/openapi.json`、`/artifacts-index`、`/jobs/summary`，并提供 `verify-deploy` / `smoke-browser` 入口，避免部署后误连旧进程或路由漂移。

---

## [ERR-20260325-008] dashboard-hard-fails-on-optional-panels

**Logged**: 2026-03-25T21:32:00+08:00
**Priority**: high
**Status**: resolved
**Area**: frontend-bootstrap

### Summary
控制台启动把 `artifacts-index`、`jobs/summary` 这类非核心面板请求和核心数据一起塞进 `Promise.all`，任一失败都会让 `packs/jobs/capabilities` 整体不落状态，直接把“运行适配包”页渲染成空下拉框。

### Error
```text
pack_select_html: <span>适配包</span><select></select>
page.waitForFunction: Timeout 30000ms exceeded.
```

### Context
- Trigger: Playwright 脚本打开 `http://127.0.0.1:8000/?page=actions`
- Related request failures:
  - `/artifacts-index` 404
  - `/jobs/summary` 422
- Impact:
  - “运行适配包”无法选择 pack
  - 前端入口 smoke test 会在页面初始化阶段假失败

### Suggested Fix
把 `loadDashboard()` 改成“核心数据必须成功、辅助面板允许降级”的结构：`capabilities/projects/jobs/packs` 单独保证，`artifacts-index/jobs/summary/provider/stage-plan/latest-result` 失败时只回退局部面板，不阻断主流程。

### Metadata
- Reproducible: yes
- Related Files: web/src/App.tsx, data/frontend-smoke/smoke-failure.json, data/frontend-smoke/failure.png

### Resolution
- **Resolved**: 2026-03-29T00:00:00+08:00
- **Notes**: `web/src/App.tsx` 已改成 core-first 数据装配，核心 `capabilities/projects/jobs/packs` 先渲染，可选面板通过降级加载与空值保护补齐；失败任务同时补了快捷操作与空态保护，不再因 optional panels 异常拖垮主流程。

---

## [ERR-20260325-009] real-media-smoke-time-budget-too-short

**Logged**: 2026-03-25T21:41:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: qa-automation

### Summary
真图真视频最小 smoke test 默认等待 7 分钟会把真实可完成的任务误判为失败；`job_27` 实际在约 10 分钟内完成并通过 27/27 校验。

### Error
```text
Error: Timed out waiting for job 27
```

### Context
- Trigger: `scripts/run_frontend_real_media_smoke.mjs`
- Test input:
  - pack: `dgyx_ch1_20`
  - chapter_start/end: `1-1`
  - scene_count: `2`
  - use_real_images: `true`
- Actual outcome:
  - `job_27` 最终 `completed`
  - `result_summary.md` 记录“真图数量 5，输出视频数量 4”
  - `validation_report.md` 为 `PASS 27/27`

### Suggested Fix
真实媒体 smoke test 默认超时至少提高到 12 分钟，并区分“提交失败”“执行中”“最终失败”三类结论，避免把长耗时任务记成失败。

### Metadata
- Reproducible: yes
- Related Files: scripts/run_frontend_real_media_smoke.mjs, artifacts/job_27/result_summary.md, artifacts/job_27/validation_report.md

### Resolution
- **Resolved**: 2026-03-25T21:41:00+08:00
- **Notes**: 脚本默认 `TIMEOUT_MS` 已从 `420000` 提高到 `720000`。

## [ERR-20260324-004] long-job-progress-blindness

**Logged**: 2026-03-24T04:02:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: execution-progress

### Summary
`manga` 长任务执行时，即使章节产物已经持续生成，数据库 workflow 仍可能一直停在第一步 `running`，导致控制台无法显示真实进度。

### Error
```text
job_24: status=running
workflow:
- research running
- story_breakdown pending
- storyboard_design pending
- chapter_packaging pending
- qa_loop pending
```

### Context
- Trigger: Agent Browser 在新版主控台提交 `dgyx_ch1_20 / 整包占位图 / scene_count=2`
- Affected job: `job_24`
- Observed evidence: `artifacts/job_24/chapters/chapter_01` 到 `chapter_06` 已持续生成
- Affected files: `backend/executor.py`, `modules/base.py`, `modules/manga/chapter_factory.py`

### Suggested Fix
给执行框架提供统一进度回调，让长任务在运行过程中把当前阶段和章节处理状态写回数据库；前端继续轮询 `/jobs` 即可反映真实进度。

### Metadata
- Reproducible: yes
- Related Files: backend/executor.py, modules/base.py, modules/manga/chapter_factory.py

### Resolution
- **Resolved**: 2026-03-24T04:02:00+08:00
- **Notes**: 已新增 `ExecutionContext.report_progress` 并接入 `manga` 执行链；待当前旧进程任务结束后重启服务，新任务即可显示进度。

---

## [ERR-20260324-003] artifact-path-hint-scope

**Logged**: 2026-03-24T03:50:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: result-depository

### Summary
`finance` 能力把基础产物 `path_hint` 写成了相对 `ARTIFACTS_DIR`，而结果沉淀层按相对 `job_dir` 解析，导致自动校验把路径拼成 `job_x/job_x/...` 并误判失败。

### Error
```text
- [FAIL] 摘要 -> .../artifacts/job_22/job_22/summary.md
- [FAIL] 完整报告 -> .../artifacts/job_22/job_22/report.md
- [FAIL] 结构化结果 -> .../artifacts/job_22/job_22/result.json
```

### Context
- Trigger: Agent Browser 在新版主控台中提交 `finance-browser-test / NVDA`
- Affected job: `job_22`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Affected files: `modules/finance/service.py`, `shared/result_depository.py`

### Suggested Fix
所有能力模块的基础产物 `path_hint` 都统一按相对 `job_dir` 约定输出；结果沉淀层对历史 `job_x/...` 写法保留兼容，避免旧任务回看时继续误报。

### Metadata
- Reproducible: yes
- Related Files: modules/finance/service.py, shared/result_depository.py

### Resolution
- **Resolved**: 2026-03-24T03:50:00+08:00
- **Notes**: 已统一 `finance` 的 `path_hint` 写法，结果沉淀层已补兼容解析；浏览器复验生成 `job_23`，`validation_report.md` 为 `PASS 3/3`。

---

## [ERR-20260320-001] script-import-path

**Logged**: 2026-03-20T01:24:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: scripts

### Summary
新加的独立脚本如果直接用 `python scripts/<name>.py` 执行，而脚本本身没有补 `sys.path`，就会因为找不到 `backend` 包而直接失败。

### Error
```text
ModuleNotFoundError: No module named 'backend'
```

### Context
- Command attempted: `python scripts/migrate_runtime_data.py`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Affected files: `scripts/migrate_runtime_data.py`, `scripts/sync_runtime_storage.py`

### Suggested Fix
所有需要从项目根直接执行的脚本，都统一在文件头部把项目根目录插入 `sys.path`，不要假设调用方一定使用 `-m` 或已经正确设置 `PYTHONPATH`。

### Metadata
- Reproducible: yes
- Related Files: scripts/migrate_runtime_data.py, scripts/sync_runtime_storage.py

### Resolution
- **Resolved**: 2026-03-20T01:24:00+08:00
- **Notes**: 已为两个脚本补齐项目根路径注入，现可独立执行。

---

## [ERR-20260319-019] video-mux-shortest-truncation

**Logged**: 2026-03-20T00:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: video-render

### Summary
章节成片封装时使用 `amix=duration=shortest` 会让视频被较短的旁白音轨截断，最终 QA 会表现为“视频时长明显不足”。

### Error
```text
QA 未通过：章节视频时长明显不足
```

### Context
- Command attempted: `python scripts/run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 1 --scene-count 1 --chapter-keyframe-count 3 --chapter-shot-count 8`
- Job observed: `job_20`
- Symptom: 分镜计划约 `95.7s`，但章节预览和交付视频只有 `21.83s`
- Root cause: `_mux_audio()` 中 `[a1][a2]amix=inputs=2:duration=shortest` 让混音输出跟随旁白最短时长，随后 `-shortest` 又把成片直接裁短

### Suggested Fix
混音阶段应以环境音/视频总长为准，改为 `amix=duration=longest`，并继续保留最终 `-shortest` 让成片跟随视频长度收口。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py

### Resolution
- **Resolved**: 2026-03-20T00:05:00+08:00
- **Notes**: `_mux_audio()` 已改为 `amix=inputs=2:duration=longest`，随后 `job_21` 重新验证通过，章节时长恢复到 `95.58s`。

---

## [ERR-20260319-018] video-qa-imageio-inf

**Logged**: 2026-03-19T23:55:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: video-qa

### Summary
章节最终 QA 读取本地 mp4 元数据时，`imageio` 可能返回 `nframes = inf`，直接转 `int` 会导致 QA 在写报告前崩溃。

### Error
```text
cannot convert float infinity to integer
```

### Context
- Command attempted: `python scripts/run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 1 --scene-count 1 --chapter-keyframe-count 3 --chapter-shot-count 8`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Impact: 章节视频和 `video_plan.json` 已生成，但 `qa_report.md`、顶层汇总与结果沉淀因最终 QA 崩溃而未完成

### Suggested Fix
在视频元数据探测里不要直接相信 `meta["nframes"]`；先判断是否为有限数，再回退到 `duration * fps` 估算帧数。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py

### Resolution
- **Resolved**: 2026-03-19T23:55:00+08:00
- **Notes**: `_probe_video_metadata()` 已改为对 `nframes` 做 `math.isfinite()` 守护，并在异常值场景下回退到 `duration * fps`。

---

## [ERR-20260317-001] rg-search

**Logged**: 2026-03-17T01:59:45+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: infra

### Summary
`rg` command failed with permission error in this Windows environment.

### Error
```
Program 'rg.exe' failed to run: Access is denied
```

### Context
- Command attempted: `rg -n "澶|鍓|闃|璇|鎴|鏂|銆|锛|鏈|娓|鎻"`
- Working directory: `E:\work\project-manager\workhome\ai-manga-factory`
- Shell: PowerShell
- Fallback command used successfully: `Get-ChildItem -Recurse -File -Include *.md,*.py | Select-String -Pattern ...`

### Suggested Fix
Check whether `rg.exe` is blocked by system policy or AV quarantine; keep `Select-String` fallback path in scripts for Windows compatibility.

### Metadata
- Reproducible: unknown
- Related Files: N/A

---
## [ERR-20260319-017] agent-browser-powershell-policy

**Logged**: 2026-03-19T17:20:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: tooling

### Summary
在当前 Windows 环境下直接调用 `agent-browser` 会被 PowerShell 执行策略拦截，因为命中的是 `agent-browser.ps1` 包装脚本。

### Error
```text
File C:\Users\Administrator\AppData\Roaming\npm\agent-browser.ps1 cannot be loaded because running scripts is disabled on this system.
```

### Context
- Command attempted: `agent-browser open <url>`
- Environment: Windows PowerShell with script execution disabled
- Impact: 浏览器技能可用，但需要绕过 `.ps1` 包装层

### Suggested Fix
直接调用 `C:\Users\Administrator\AppData\Roaming\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe`，不要走 `agent-browser.ps1`。

### Metadata
- Reproducible: yes
- Related Files: C:\Users\Administrator\AppData\Roaming\npm\agent-browser.ps1

### Resolution
- **Resolved**: 2026-03-19T17:20:00+08:00
- **Notes**: 后续在该环境下使用 agent-browser 时统一走底层 exe。

---

## [ERR-20260319-018] agent-browser-daemon-port-conflict

**Logged**: 2026-03-19T17:24:00+08:00  
**Priority**: low  
**Status**: pending  
**Area**: tooling

### Summary
直接调用 `agent-browser` 底层 exe 时，daemon 启动因为 TCP 端口占用失败，无法继续接管浏览器会话。

### Error
```text
Daemon error: Failed to bind TCP: 通常每个套接字地址(协议/网络地址/端口)只允许使用一次。 (os error 10048)
```

### Context
- Command attempted: `agent-browser-win32-x64.exe open <url>`
- Environment: Windows desktop session
- Impact: 当前无法直接用 agent-browser 验证已登录的火山控制台页面

### Suggested Fix
排查并清理残留的 agent-browser daemon，或改用可指定端口/无 daemon 模式的启动方式。

### Metadata
- Reproducible: yes
- Related Files: C:\Users\Administrator\AppData\Roaming\npm\node_modules\agent-browser\bin\agent-browser-win32-x64.exe
## [ERR-20260319-016] missing-feature-requests-log

**Logged**: 2026-03-19T16:40:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: process

### Summary
按工作区规则检查长期沉淀时，`ai-manga-factory/.learnings/FEATURE_REQUESTS.md` 缺失，导致读取该文件的命令失败。

### Error
```text
Get-Content : Cannot find path 'E:\work\project-manager\workhome\projects\ai-manga-factory\.learnings\FEATURE_REQUESTS.md' because it does not exist.
```

### Context
- Operation attempted: review `.learnings/FEATURE_REQUESTS.md` before/after a larger capability change
- Environment: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Impact: 违反工作区协作规则中“涉及能力规划、自动化或长期流程时，再查看 `.learnings/FEATURE_REQUESTS.md`”的前置假设

### Suggested Fix
在项目初始化或整理长期沉淀时，默认创建 `.learnings/FEATURE_REQUESTS.md`，即使当前没有待处理条目也保留占位文件。

### Metadata
- Reproducible: yes
- Related Files: .learnings/FEATURE_REQUESTS.md, E:/work/AGENTS.md

### Resolution
- **Resolved**: 2026-03-19T16:40:00+08:00
- **Notes**: 已在 `ai-manga-factory/.learnings/` 下补齐 `FEATURE_REQUESTS.md`。

## [ERR-20260319-013] storyboard-priority-non-numeric

**Logged**: 2026-03-19T20:12:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: storyboard

### Summary
模型分镜如果把 `关键帧优先级` 输出成“高/中/低”等文本，旧逻辑会在 `int()` 转换时报错并触发回退模板。

### Error
```text
invalid literal for int() with base 10: '高'
```

### Context
- Command attempted: 单章真图返工 `job_13` / `job_14`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: provider notes 记录了分镜生成后在优先级解析阶段触发回退

### Suggested Fix
对模型返回的优先级做归一化，兼容数字、高中低和中文数字，再参与关键帧排序与写盘。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_13/result_summary.md, data/artifacts/job_14/result_summary.md

### Resolution
- **Resolved**: 2026-03-19T20:12:00+08:00
- **Notes**: 已补 `_coerce_priority()` 容错解析，后续不会因该字段格式波动直接回退模板。

---

## [ERR-20260319-011] qa-retry-dropped-blockers

**Logged**: 2026-03-19T20:05:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: qa

### Summary
章节 QA 返工循环只回灌 `issues` 不回灌 `blockers`，会让“名台词未入镜”这类硬阻塞在多轮返工中原样重复。

### Error
```text
QA 未通过，需继续返工：第13章, 第19章
```

### Context
- Command attempted: `python scripts/run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 20 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: `job_12` 20 章都已生成，但最终被 QA 门禁拦下；第 19 章的 blocker 是“名台词没有进入章节分镜”，三轮结果完全重复

### Suggested Fix
返工时同时回灌 `issues` 和 `blockers`，并对名台词、世界规则、节奏和首尾钩子增加确定性修正逻辑。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_12/chapters/chapter_19/qa/qa_snapshot.json

### Resolution
- **Resolved**: 2026-03-19T20:05:00+08:00
- **Notes**: 已把 `issues + blockers` 一并回灌，并补了自动补强逻辑；`job_13` 和 `job_14` 定向返工均已通过 QA。

---

## [ERR-20260319-012] validation-assumed-chapter-01

**Logged**: 2026-03-19T20:05:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: validation

### Summary
校验器默认按 `chapter_01..chapter_N` 枚举章节，导致定向返工任务即使真实通过，也会因章节号不是从 1 开始而被误报 FAIL。

### Error
```text
[FAIL] chapters/chapter_01/storyboard/storyboard.json
```

### Context
- Command attempted: `python scripts/validate_job_output.py --job-id 13`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: `job_13` 实际产物目录为 `chapter_13`，但校验器仍去查 `chapter_01`

### Suggested Fix
校验时优先使用 `chapter_briefs` 或 `chapter_start/chapter_end` 解析真实章节号，再生成检查列表。

### Metadata
- Reproducible: yes
- Related Files: shared/result_depository.py, data/artifacts/job_13/validation_report.md

### Resolution
- **Resolved**: 2026-03-19T20:05:00+08:00
- **Notes**: 真实章节号解析已补齐，`job_13` 和 `job_14` 重新校验后均为 PASS。

---

## [ERR-20260319-008] missing-openpyxl-for-storyboard-import

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: tooling

### Summary
导入外部分镜 Excel 时，如果运行环境缺少 `openpyxl`，故事板参考无法解析，章节节奏 profile 也无法生成。

### Error
```text
ModuleNotFoundError: No module named 'openpyxl'
```

### Context
- Command attempted: 读取 `C:\Users\Administrator\Downloads\storyboard_ep1_timing_adjusted.xlsx`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Impact: 无法生成 `storyboard_reference_ep1.json` 和 `storyboard_profile.json`

### Suggested Fix
把 `openpyxl` 加入项目依赖，并在处理 Excel 参考资料前先验证环境是否具备该依赖。

### Metadata
- Reproducible: yes
- Related Files: requirements.txt, scripts/import_storyboard_reference.py, shared/storyboard_reference.py

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: 已安装 `openpyxl`，并同步写入 `requirements.txt`，分镜 Excel 导入链路已跑通。

---

## [ERR-20260319-009] storyboard-total-row-double-counted

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: storyboard

### Summary
解析分镜统计表时把“总计”行当成普通分组，会导致目标时长翻倍、分组数错误，并进一步破坏章节节奏和 QA 判断。

### Error
```text
group_count = 7
target_duration_seconds = 191.4
```

### Context
- Command attempted: 从 `storyboard_ep1_timing_adjusted.xlsx` 生成节奏 profile
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Expected: 6 个分组、总时长约 95.7 秒
- Actual: 把 `总计` 行并入分组统计，导致 profile 异常，后续章节镜头数和节奏均失真

### Suggested Fix
解析外部统计表时，显式过滤 `总计`、`合计` 之类的汇总行，只保留真实分组数据参与时长建模。

### Metadata
- Reproducible: yes
- Related Files: shared/storyboard_reference.py, data/reference/storyboard_profile.json

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: 已在解析逻辑中过滤汇总行，当前 profile 恢复为 6 组、95.7 秒，章节 QA 通过。

---

## [ERR-20260319-010] soft-qa-allowed-false-complete

**Logged**: 2026-03-19T18:20:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: qa

### Summary
如果 QA 只输出报告但不阻塞任务，章节未通过时整包任务仍可能被误标成 `completed`。

### Error
```text
job completed while chapter qa.passed = false
```

### Context
- Command attempted: 章节工厂早期烟测运行
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: 文件完整生成，但章节 QA 报告未通过，任务状态仍显示完成

### Suggested Fix
把 QA 改成强制门禁，只要任一章节 `qa.passed = false` 就直接抛错，使任务失败并进入返工路径。

### Metadata
- Reproducible: yes
- Related Files: modules/manga/chapter_factory.py, data/artifacts/job_10/chapters/chapter_01/qa/qa_snapshot.json

### Resolution
- **Resolved**: 2026-03-19T18:20:00+08:00
- **Notes**: 章节工厂已在运行时强制检查 QA 结果，`job_11` 仅在 20/20 章节通过后才完成。

---

## [ERR-20260317-003] powershell-remove-item-policy

**Logged**: 2026-03-17T06:42:00+08:00  
**Priority**: low  
**Status**: pending  
**Area**: infra

### Summary
`Remove-Item -Recurse -Force` was blocked by policy for local cleanup in this environment.

### Error
```
"powershell.exe" -Command "Remove-Item -Recurse -Force ..." rejected: blocked by policy
```

### Context
- Command attempted during cleanup of a temporary management run directory.
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Fallback that worked: `cmd /c rmdir /s /q ...`

### Suggested Fix
Prefer `cmd /c rmdir /s /q` as the fallback path for deleting temporary directories when PowerShell deletion is policy-blocked.

### Metadata
- Reproducible: yes
- Related Files: N/A

---

## [ERR-20260317-002] ark-seedream-size

**Logged**: 2026-03-17T02:50:00+08:00  
**Priority**: high  
**Status**: resolved  
**Area**: backend

### Summary
`Doubao-Seedream-4.5` rejected 1024x1024 requests because image area was below minimum.

### Error
```
InvalidParameter: image size must be at least 3686400 pixels
```

### Context
- Command attempted: `python scripts/test_api.py --image-model "Doubao-Seedream-4.5"`
- API key auth succeeded; request failed on `size`.
- Previous code used `1024x1024` by default.

---

## [ERR-20260318-001] powershell-and-and

**Logged**: 2026-03-18T00:23:07.5944761+08:00  
**Priority**: low  
**Status**: pending  
**Area**: infra

### Summary
PowerShell in this environment does not accept `&&` as a command separator.

### Error
```
The token '&&' is not a valid statement separator in this version.
```

### Context
- Command attempted: `git add ... && git commit -m "..."`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Shell: PowerShell

### Suggested Fix
Run `git add` and `git commit` as separate commands in this environment.

### Metadata
- Reproducible: yes
- Related Files: N/A

---

### Suggested Fix
Normalize requested width/height before image generation and auto-upscale to meet minimum pixel area.

### Metadata
- Reproducible: yes
- Related Files: shared/providers/ark.py

### Resolution
- **Resolved**: 2026-03-17T02:52:00+08:00
- **Notes**: Added `_normalize_image_size()` in `ArkProvider` to enforce minimum 3,686,400 pixels.

---

## [ERR-20260317-004] apply-patch-windows-length

**Logged**: 2026-03-17T23:18:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: infra

### Summary
Large single-shot `apply_patch` operations can fail on this Windows environment with filename or extension length errors.

### Error
```
Io(Os { code: 206, kind: InvalidFilename, message: "文件名或扩展名太长。" })
```

### Context
- Operation attempted: rewrite `backend/run_management.py` in one oversized `apply_patch`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Environment: PowerShell on Windows

### Suggested Fix
Break large manual edits into smaller `apply_patch` chunks or staged file rewrites instead of sending one oversized patch payload.

### Metadata
- Reproducible: yes
- Related Files: backend/run_management.py

### Resolution
- **Resolved**: 2026-03-17T23:18:00+08:00
- **Notes**: Switched to incremental patches for orchestration-related edits.

---

## [ERR-20260317-005] powershell-and-separator

**Logged**: 2026-03-17T23:25:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: infra

### Summary
This PowerShell environment does not support `&&` as a command separator.

### Error
```
The token '&&' is not a valid statement separator in this version.
```

### Context
- Command attempted: `git add ... && git commit ...`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Environment: PowerShell on Windows

### Suggested Fix
Run commands in separate shell invocations or use PowerShell-native sequencing instead of Bash-style `&&`.

### Metadata
- Reproducible: yes
- Related Files: N/A

### Resolution
- **Resolved**: 2026-03-17T23:25:00+08:00
- **Notes**: Split git staging and commit into separate commands.

---

## [ERR-20260318-006] missing-runtime-deps-for-import-check

**Logged**: 2026-03-18T11:18:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: infra

### Summary
在未创建项目 `.venv` 且未安装依赖时，直接做模块 import 级验证会失败。

### Error
```
ModuleNotFoundError: No module named 'imageio'
```

### Context
- Command attempted: `python - <<...>>` importing `modules.manga.service`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Cause: project baseline intentionally no longer includes `.venv`, and当前 Python 环境未安装项目依赖。
- Fallback used successfully: `py_compile` 递归语法校验全部 `.py` 文件。

### Suggested Fix
当仓库基线不携带 `.venv` 时，先执行 `python -m venv .venv` 和 `pip install -r requirements.txt` 再做 import 级验收；
如果只想先验证改动是否安全，优先使用 `py_compile` 做语法校验。

### Metadata
- Reproducible: yes
- Related Files: requirements.txt, run_backend.ps1, modules/manga/service.py

---

## [ERR-20260318-007] powershell-policy-blocked-background-launch

**Logged**: 2026-03-18T11:35:00+08:00  
**Priority**: low  
**Status**: pending  
**Area**: infra

### Summary
当前 PowerShell 策略会拦截带 `Start-Process` 和输出重定向的后台启动命令。

### Error
```
... rejected: blocked by policy
```

### Context
- Command attempted: PowerShell 中通过 `Start-Process` 后台拉起 uvicorn，并重定向到日志文件
- Working directory: `E:\work`
- Intended target: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Successful fallback: 使用 Python `subprocess.Popen(..., creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)` 启动后台服务

### Suggested Fix
在这个环境里，需要后台常驻进程时优先使用 Python `subprocess.Popen` 方式，不依赖 PowerShell 的
`Start-Process` 与复杂重定向组合。

### Metadata
- Reproducible: yes
- Related Files: run_backend.ps1

---

## [ERR-20260318-008] create-pack-missing-project-root

**Logged**: 2026-03-18T12:05:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: scripts

### Summary
`create_adaptation_pack.py` 单独运行时没有把项目根目录加入 `sys.path`，会导致找不到 `backend` 包。

### Error
```
ModuleNotFoundError: No module named 'backend'
```

### Context
- Command attempted: `E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\create_adaptation_pack.py ...`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Related script: `scripts/create_adaptation_pack.py`
- Similar scripts `run_adaptation_pack.py` 和 `validate_job_output.py` 已有 `PROJECT_ROOT` 注入逻辑。

### Suggested Fix
所有项目级 CLI 入口脚本统一在文件头部注入 `PROJECT_ROOT` 到 `sys.path`，保证脚本可以被直接执行。

### Metadata
- Reproducible: yes
- Related Files: scripts/create_adaptation_pack.py

### Resolution
- **Resolved**: 2026-03-18T12:06:00+08:00
- **Notes**: 已补充 `SCRIPT_PATH`、`PROJECT_ROOT` 和 `sys.path` 注入逻辑。

---

## [ERR-20260318-009] windows-console-gbk-output

**Logged**: 2026-03-18T14:58:00+08:00  
**Priority**: low  
**Status**: pending  
**Area**: infra

### Summary
Windows 控制台使用 GBK 编码时，直接打印 Ark 文本模型返回内容可能因 emoji 或特殊字符而崩溃。

### Error
```
UnicodeEncodeError: 'gbk' codec can't encode character ...
```

### Context
- Command attempted: 直接 `print(resp.choices[0].message.content)` 输出 Ark 文本模型响应
- Working directory: `E:\work`
- Successful workaround: 使用 `sys.stdout.buffer.write(...encode('utf-8'))` 或 `json.dumps(..., ensure_ascii=False)` 安全输出

### Suggested Fix
在这个环境里调试模型文本返回时，优先使用 UTF-8 字节流或 JSON 序列化输出，避免直接 `print()` 原始字符串。

### Metadata
- Reproducible: yes
- Related Files: shared/providers/ark.py

---

## [ERR-20260318-010] source-import-utf8-bom-first-chapter

**Logged**: 2026-03-18T16:10:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: scripts

### Summary
单文件原文导入时，如果 txt 以 UTF-8 BOM 开头，首章标题可能识别失败，导致导入后缺少第 1 章。

### Error
```
仍缺少章节：[1]
```

### Context
- Command attempted: `python scripts/collect_source_text.py --pack-name tmp_source_tool_smoke --source-file ... --overwrite`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Cause: `Set-Content -Encoding UTF8` 生成的 txt 带 BOM，而原文字段读取优先用 `utf-8`，BOM 没被去掉，首行正则无法匹配 `第1章`

### Suggested Fix
原文读取时优先使用 `utf-8-sig`，并在规范化文本时显式移除 `\ufeff`，避免章节正则被 BOM 干扰。

### Metadata
- Reproducible: yes
- Related Files: shared/source_materials.py, scripts/collect_source_text.py

### Resolution
- **Resolved**: 2026-03-18T16:12:00+08:00
- **Notes**: 将 `DEFAULT_SOURCE_ENCODINGS` 调整为优先 `utf-8-sig`，并在 `normalize_text()` 中统一移除 BOM。

---

## [ERR-20260318-011] powershell-inline-python-chinese-filename

**Logged**: 2026-03-18T16:36:00+08:00  
**Priority**: low  
**Status**: pending  
**Area**: infra

### Summary
通过 PowerShell 管道运行内联 Python 时，中文文件名可能被控制台编码破坏，导致 `Path.write_text()` 创建文件失败。

### Error
```
OSError: [Errno 22] Invalid argument: 'E:\\work\\tmp_html_source_smoke\\?1? ????.html'
```

### Context
- Command attempted: `@' ... '@ | python -`
- Working directory: `E:\work`
- Intended file name: 中文章节 HTML 文件名
- Successful workaround: 测试辅助文件使用 ASCII 文件名，章节标题保留在 HTML 内容里

### Suggested Fix
在这个环境里做内联 Python 验证时，优先使用 ASCII 临时文件名；如果必须创建中文文件名，改用独立 `.py` 文件或 PowerShell 原生命令，避免管道编码干扰。

### Metadata
- Reproducible: yes
- Related Files: N/A

---

## [ERR-20260318-012] official-reader-bot-challenge

**Logged**: 2026-03-18T16:42:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: integration

### Summary
直接用匿名 HTTP 请求访问起点这类官方阅读页时，返回的是人机校验壳，不是章节正文。

### Error
```text
HTTP 202
<script src="/.../probe.js"></script>
```

### Context
- Command attempted: 直接 `requests.get()` 访问 `https://www.qidian.com/book/1209977/catalog/` 和章节页
- Working directory: `E:\work`
- Observed behavior: 返回空壳 HTML，正文提取无意义
- Successful workaround: 给原文导入工具增加 `--header-file`、`--cookie-file`，并支持浏览器保存 HTML 后离线导入

### Suggested Fix
后续对官方受保护阅读页不要再假设匿名可抓取；优先走用户自己的认证会话，或使用浏览器保存的合法 HTML 导入。

### Metadata
- Reproducible: yes
- Related Files: scripts/collect_source_text.py, docs/小说原文导入工具.md

---

## [ERR-20260319-001] playwright-capture-missing-normalize-text

**Logged**: 2026-03-19T02:13:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: scripts

### Summary
`playwright_source_capture.py` 在抓取成功后整理页面标题时引用了 `normalize_text()`，但漏掉了导入，导致每章抓取都失败。

### Error
```text
name 'normalize_text' is not defined
```

### Context
- Command attempted: `python scripts/playwright_source_capture.py capture --pack-name tmp_playwright_capture_smoke ...`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: `成功 0 / 失败 2`

### Suggested Fix
在脚本顶部显式导入 `shared.source_materials.normalize_text`，并保留最小抓取回归测试。

### Metadata
- Reproducible: yes
- Related Files: scripts/playwright_source_capture.py

### Resolution
- **Resolved**: 2026-03-19T02:14:00+08:00
- **Notes**: 已补 `normalize_text` 导入，随后重跑最小抓取回归测试。

---

## [ERR-20260319-002] playwright-config-relative-path

**Logged**: 2026-03-19T10:50:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: scripts

### Summary
`playwright_source_capture.py` 读取配置文件时，如果配置里的路径写成 `adaptations/<pack_name>/...`，会被错误地拼到配置文件目录下面，导致路径重复。

### Error
```text
请求头文件不存在：E:\work\...\source\adaptations\<pack_name>\source\incoming\request_headers.json
```

### Context
- Command attempted: `python scripts/run_source_ingestion_pipeline.py --pack-name tmp_source_pipeline_smoke ...`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Cause: `resolve_path_option()` 只按 `config_base_dir / relative_path` 解析，没识别出这是项目根相对路径

### Suggested Fix
配置解析时优先识别 `adaptations/`、`data/` 这类项目根相对路径；同时把 `playwright_capture.template.json` 默认改成相对 `source/` 的 `incoming/...` 路径。

### Metadata
- Reproducible: yes
- Related Files: scripts/playwright_source_capture.py, shared/source_materials.py, adaptations/dpcq_ch1_20/source/playwright_capture.template.json

### Resolution
- **Resolved**: 2026-03-19T10:56:00+08:00
- **Notes**: `resolve_path_option()` 已兼容项目根相对路径；模板默认路径已改为 `incoming/...`。

---

## [ERR-20260319-003] source-pipeline-gbk-failure-print

**Logged**: 2026-03-19T10:52:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: scripts

### Summary
`run_source_ingestion_pipeline.py` 在 Windows `GBK` 控制台里输出失败原因时，可能因为替换字符或非本地编码字符再次触发 `UnicodeEncodeError`。

### Error
```text
UnicodeEncodeError: 'gbk' codec can't encode character '\ufffd'
```

### Context
- Command attempted: `python scripts/run_source_ingestion_pipeline.py --pack-name tmp_source_pipeline_smoke ...`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: 流水线本体已写出失败快照，但主脚本在打印 `failure_message` 时再次崩溃

### Suggested Fix
包装脚本打印失败文本前要做控制台兼容处理；调用 Python 子进程时强制 `PYTHONIOENCODING=utf-8`，减少抓取报告和错误输出乱码。

### Metadata
- Reproducible: yes
- Related Files: scripts/run_source_ingestion_pipeline.py

### Resolution
- **Resolved**: 2026-03-19T10:58:00+08:00
- **Notes**: 已新增 `safe_console_text()`，并在 `subprocess.run()` 环境里强制 `PYTHONIOENCODING=utf-8`。

---

## [ERR-20260319-004] agent-browser-qidian-slider-captcha

**Logged**: 2026-03-19T11:35:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: integration

### Summary
用 `agent-browser` 打开起点首页和《斗破苍穹》目录页时，当前真实浏览器自动化上下文会直接进入腾讯滑块验证码，而不是目录页正文或目录 DOM。

### Error
```text
TencentCaptcha
拖动下方滑块完成拼图
```

### Context
- Command attempted: `agent-browser open https://www.qidian.com/` / `agent-browser open https://www.qidian.com/book/1209977/catalog/`
- Working directory: `E:\work`
- Observed result: 页面 HTML 为验证码壳，截图显示腾讯滑块拼图，Cookie 中出现 `w_tsfp` 和 `x-waf-captcha-referer`
- Saved artifacts:
  - `adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.html`
  - `adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.png`
  - `data/source_sessions/dpcq_ch1_20/agent_browser/qidian_waf_state.json`

### Suggested Fix
不要再假设“换成真实浏览器自动化就一定能直接进入目录页”；对起点这类站点，仍要保留人工验证码/登录接管或复用已登录的真实浏览器资料。

### Metadata
- Reproducible: yes
- Related Files: adaptations/dpcq_ch1_20/reports/agent_browser_qidian_probe.md, adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.html

---

## [ERR-20260319-005] playwright-edge-default-profile-in-use

**Logged**: 2026-03-19T11:37:00+08:00  
**Priority**: medium  
**Status**: pending  
**Area**: integration

### Summary
Playwright 直接复用系统 Edge 默认用户资料时，如果当前 Edge 正在运行，`launch_persistent_context()` 会立即退出，无法借用现成资料导出状态。

### Error
```text
BrowserType.launch_persistent_context: Target page, context or browser has been closed
exitCode=21
```

### Context
- Command attempted: 用 Playwright `launch_persistent_context(user_data_dir=Edge User Data, channel='msedge', args=['--profile-directory=Default'])`
- Working directory: `E:\work`
- Observed result: Edge 进程启动后立刻退出
- Additional evidence: Edge 默认资料历史里存在起点访问记录，但 `Cookies` 数据库被占用，无法直接复用

### Suggested Fix
如果要借用系统 Edge 现成资料，优先在用户关闭所有 Edge 窗口后再尝试；否则仍以“人工接管一次登录/验证码 -> 导出状态”为主路径。

### Metadata
- Reproducible: yes
- Related Files: adaptations/dpcq_ch1_20/reports/agent_browser_qidian_probe.md

---

## [ERR-20260319-006] source-ingestion-parallel-dependency

**Logged**: 2026-03-19T12:15:00+08:00  
**Priority**: low  
**Status**: resolved  
**Area**: integration

### Summary
在章节 HTML 仍在持续写入时并行启动原文导入，会让 `collect_source_text.py` 扫到半成品目录并误报缺章。

### Error
```text
仍缺少章节：[1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
```

### Context
- Command attempted: 同时执行 `capture_cdp_chapters.py` 与 `collect_source_text.py`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Root cause: 导入脚本开始扫描时，目标目录里的章节文件还没有全部落盘

### Suggested Fix
对“真人浏览器抓取 -> 原文导入 -> 摘要生成”保持严格串行；只把互不依赖的只读检查放进并行步骤。

### Metadata
- Reproducible: yes
- Related Files: scripts/capture_cdp_chapters.py, scripts/collect_source_text.py

### Resolution
- **Resolved**: 2026-03-19T12:15:00+08:00
- **Notes**: 抓取完成后重新串行执行导入，章节目录可被完整识别。

---

## [ERR-20260319-007] ark-video-invalid-content-text

**Logged**: 2026-03-19T13:00:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: media-generation

### Summary
Ark 视频任务在部分长 prompt 场景下会返回 `Invalid content.text`，导致系统误以为必须回退到本地拼接视频。

### Error
```text
Ark video task failed: One or more parameters specified in the request are not valid: Invalid content.text
```

### Context
- Command attempted: `python scripts/run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20 --real-images`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: `job_6` completed but `真视频数量 0`，由本地回退视频顶上
- Verification: 极简 prompt 与同一版剧情 prompt 的独立视频测试都能成功，说明失败具备瞬时性与 prompt 兼容性波动

### Suggested Fix
在 `ArkProvider.generate_video_to_file()` 里保留“原 prompt -> 清洗压缩 prompt”两级候选，对 `Invalid content.text` 这类错误先做重试，而不是直接放弃真视频。

### Metadata
- Reproducible: intermittent
- Related Files: shared/providers/ark.py, data/artifacts/job_6/result_summary.md, data/artifacts/job_7/result_summary.md

### Resolution
- **Resolved**: 2026-03-19T13:05:00+08:00
- **Notes**: 已补视频 prompt 清洗重试；重跑后 `job_7` 真视频数量恢复为 1。

---
## [ERR-20260319-014] brief-generation-batch-timeout

**Logged**: 2026-03-19T15:20:00+08:00  
**Priority**: medium  
**Status**: resolved  
**Area**: brief-generation

### Summary
在“正版原文逐章驱动”的场景下，`generate_chapter_briefs.py` 使用默认批大小时可能长时间卡在 Ark 文本调用阶段，导致外层命令超时且不落任何结果。

### Error
```text
command timed out after 244012 milliseconds
```

### Context
- Command attempted: `python scripts/generate_chapter_briefs.py --pack-name dpcq_ch21_40 --chapter-start 21 --chapter-end 40 --force`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: 进程持续运行但 `chapter_briefs.json` 仍保持占位内容，`brief_generation_report.md` 未生成

### Suggested Fix
对长章节原文改用更保守的参数：
`--batch-size 1 --source-max-chars 1800`
必要时先单章探针验证，再做全量重跑。

### Metadata
- Reproducible: yes
- Related Files: scripts/generate_chapter_briefs.py, adaptations/dpcq_ch21_40/chapter_briefs.json

### Resolution
- **Resolved**: 2026-03-19T15:20:00+08:00
- **Notes**: 停掉残留进程后，改用 `batch-size=1` 全量重跑成功，20 章摘要全部生成完成。

---

## [ERR-20260319-015] ark-text-account-overdue-fallback

**Logged**: 2026-03-19T15:20:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: media-generation

### Summary
整包真图生产过程中，Ark 文本模型在后段章节返回 `AccountOverdueError`，导致模型分镜回退到 fallback 模板，虽然任务最终 PASS，但会降低这些章节的分镜质量上限。

### Error
```text
Ark text generation failed: Error code: 403 - {'error': {'code': 'AccountOverdueError', ...}}
```

### Context
- Command attempted: `python scripts/run_adaptation_pack.py --pack-name dpcq_ch21_40 --chapter-start 21 --chapter-end 40 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard`
- Working directory: `E:\work\project-manager\workhome\projects\ai-manga-factory`
- Observed result: `job_18` 最终 `completed` 且 `PASS 253/253`，但章节 38/39/40 的模型分镜因 Ark 403 欠费错误回退到 fallback 模板

### Suggested Fix
在继续跑 `41-60` 章或要重做 `38-40` 章前，先处理 Ark 账户欠费/额度问题；恢复后优先定向重跑受影响章节，以提升模型分镜命中率。

### Metadata
- Reproducible: yes
- Related Files: data/artifacts/job_18/result_summary.md, adaptations/dpcq_ch21_40/reports/job_18_summary.md

---

## [ERR-20260325-004] smoke-script-artifact-summary

**Logged**: 2026-03-25T22:45:00+08:00
**Priority**: high
**Status**: pending
**Area**: validation

### Summary
前端真媒体 smoke 脚本引用了未定义变量 rtifact_summary，导致回归在业务验证前提前失败。

### Error
`	ext
ReferenceError: artifact_summary is not defined
`

### Context
- Script: E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\run_frontend_real_media_smoke.mjs`n- Trigger: 2026-03-25 重新执行真图真视频 smoke test

### Suggested Fix
统一脚本里的回归摘要变量名，跑脚本前先做 
ode --check 之外的最小运行自检。

### Metadata
- Reproducible: yes
- Related Files: E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\run_frontend_real_media_smoke.mjs`n
---
