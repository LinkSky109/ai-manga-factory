# Codex额度节省执行方案

## 目标

在 Codex 周额度紧张时，继续推进 AI 漫剧工厂，但把重复执行、批处理、验证和结果沉淀尽量交给本地脚本，减少 Codex 只做高价值决策和改造。

## 原则

1. 把 Codex 用在“决定方向、改代码、查问题、补架构”。
2. 把机器重复活交给本地脚本。
3. 尽量把问题打包后一次性提问，不要碎片化多轮往返。
4. 先跑本地验证，再把失败结果一次性交给 Codex 分析。

## 现在就能直接本地做的事

### 1. 启动后端

Windows：

```bat
E:\work\project-manager\workhome\projects\ai-manga-factory\start.bat
```

Git Bash / bash：

```bash
/e/work/project-manager/workhome/projects/ai-manga-factory/start.sh
```

### 2. 跑整包生产并自动校验

Windows：

```bat
E:\work\project-manager\workhome\projects\ai-manga-factory\run_pack.bat dpcq_ch1_20 20 placeholder
```

真图模式：

```bat
E:\work\project-manager\workhome\projects\ai-manga-factory\run_pack.bat dpcq_ch1_20 20 real
```

Linux / Git Bash：

```bash
/e/work/project-manager/workhome/projects/ai-manga-factory/start.sh pack dpcq_ch1_20 20 real
```

### 3. 只做结果复验

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\validate_job_output.py --pack-name dpcq_ch1_20
```

### 4. 导入原文

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\collect_source_text.py --pack-name dpcq_ch1_20 --source-dir E:\novels\dpcq --chapter-start 1 --chapter-end 20 --overwrite
```

### 5. 重生成章节摘要

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\generate_chapter_briefs.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 20 --force
```

## 最省额度的工作流

### A. 日常执行

1. 你先本地跑原文导入、摘要生成、整包生产、自动校验。
2. 只在下面 4 种情况再叫 Codex：
   - 代码要改
   - QA 失败原因不清楚
   - 模型调用策略要改
   - 业务流程要扩展

### B. 一次性把材料发给 Codex

每次尽量一次性带上：

- 目标
- 命令
- 失败日志
- 产物路径
- 你希望的结果

推荐格式：

```text
目标：让第 21-40 章通过真实图生视频 QA
已执行：run_pack.bat dpcq_ch21_40 20 real
失败位置：job_XX / validation_report.md / qa_report.md
我希望你做：定位问题、改代码、补文档、告诉我如何复跑
```

这样比多轮零散追问更省额度。

## 哪些事情优先本地跑

- `run_pack.bat`
- `validate_job_output.py`
- `collect_source_text.py`
- `generate_chapter_briefs.py`
- `run_source_ingestion_pipeline.py`

## 哪些事情更值得用 Codex

- 视频接口接法是否正确
- QA 门禁设计
- 模型路由与额度监控
- 适配包结构升级
- 前后端功能新增
- 原因复杂的失败排查

## 当前建议

如果你这个星期额度已经紧张，最稳的办法是：

1. 先只用本地脚本推进原文、摘要、跑包、校验。
2. 把失败批次和日志攒成一批。
3. 再找 Codex 一次性处理“高价值问题包”。

## 本项目里最有用的入口

- 启动后端：`start.bat`
- Windows 跑包：`run_pack.bat`
- 跨平台跑包：`start.sh pack ...`
- 结果复验：`scripts/validate_job_output.py`
- 原文导入：`scripts/collect_source_text.py`
- 摘要生成：`scripts/generate_chapter_briefs.py`

## 结论

额度紧张时，不要停止项目，而是把 Codex 从“执行器”切成“高价值调度器”。这套项目现在已经具备本地独立推进的基础，你只需要把本地跑出来的问题一次性交给 Codex 处理。
