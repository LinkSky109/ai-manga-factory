# AI 漫剧工厂操作手册

## 1. 你现在会用到什么

AI 漫剧工厂已经整理成一个纯业务项目，主要包含四部分：

- 后端 API：负责任务创建、任务执行、任务查询
- 中文前端：浏览器里直接操作任务和适配包
- 适配包：把某部小说的章节输入整理成可执行配置
- 自动沉淀：每次任务结束后自动生成摘要、校验报告、结果快照

项目目录：

- 项目根目录：`E:\work\project-manager\workhome\projects\ai-manga-factory`
- 默认虚拟环境：`E:\work\.venvs\ai-manga-factory`

## 2. 第一次启动

### 2.1 创建虚拟环境

```powershell
python -m venv E:\work\.venvs\ai-manga-factory
```

### 2.2 安装依赖

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe -m pip install -r E:\work\project-manager\workhome\projects\ai-manga-factory\requirements.txt
```

### 2.3 启动后端

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
.\start.bat
```

如果你在 Git Bash、WSL 或其他 bash 环境里启动，用：

```bash
cd /e/work/project-manager/workhome/projects/ai-manga-factory
./start.sh
```

`start.bat` 和 `start.sh` 都会优先使用：

- `AI_MANGA_FACTORY_PYTHON`
- `E:\work\.venvs\ai-manga-factory`
- 项目内 `.venv`

### 2.4 打开页面

浏览器打开：

- `http://127.0.0.1:8000`

## 3. 页面怎么用

### 3.1 创建通用任务

左侧“创建任务”区域可以直接新建任务。

操作步骤：

1. 选择能力
2. 填项目名
3. 填参数
4. 点击“创建并执行”

适用场景：

- 单次试跑
- 手动验证模块
- 不想先做适配包时的快速实验

### 3.2 跑一个小说适配包

左侧“适配包执行器”区域用于批量跑小说章节。

可选动作：

- 运行整包
- 整包真图模式
- 分批运行
- 分批真图模式

建议：

- 先用占位模式跑通
- 确认章节摘要和流程没问题后，再切真图模式

### 3.3 看结果

右侧“任务列表”会显示：

- 任务状态
- 执行步骤
- 产物链接
- 自动沉淀结果

## 4. 怎么新建一部小说

以《斗破苍穹》前 20 章为例。

### 4.1 创建适配包

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\create_adaptation_pack.py --pack-name dpcq_ch1_20 --source-title "斗破苍穹" --chapter-start 1 --chapter-end 20
```

会生成：

- `adaptations\dpcq_ch1_20\pack.json`
- `adaptations\dpcq_ch1_20\chapter_briefs.json`
- `adaptations\dpcq_ch1_20\README.md`
- `adaptations\dpcq_ch1_20\reports\README.md`

### 4.2 补章节摘要

编辑：

- `E:\work\project-manager\workhome\projects\ai-manga-factory\adaptations\dpcq_ch1_20\chapter_briefs.json`

每章至少补这几个字段：

- `chapter`
- `title`
- `summary`
- `key_scene`
- `emotion`

如果要直接调用模型自动生成：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\generate_chapter_briefs.py --pack-name dpcq_ch1_20
```

### 4.3 跑整包

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20
```

### 4.4 重新做校验

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\validate_job_output.py --pack-name dpcq_ch1_20
```

## 5. 怎么启用真图和真视频

优先方式是把 key 放到：

- `E:\work\project-manager\workhome\projects\ai-manga-factory\secrets\ark_api_key.txt`

也可以用环境变量：

```powershell
$env:ARK_API_KEY="你的 key"
```

然后执行真图模式：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20 --real-images
```

## 6. 自动沉淀会写到哪里

每个任务都会写：

- `data\artifacts\job_<id>\result_summary.md`
- `data\artifacts\job_<id>\validation_report.md`
- `data\artifacts\job_<id>\result_snapshot.json`
- `data\artifacts\job_<id>\preview\preview.mp4`
- `data\artifacts\job_<id>\delivery\final_cut.mp4`

如果任务属于适配包，还会同步写：

- `adaptations\<pack_name>\reports\latest_result.md`
- `adaptations\<pack_name>\reports\latest_validation.md`
- `adaptations\<pack_name>\reports\result_journal.md`

## 7. 常用命令汇总

### 启动服务

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
.\start.bat
```

### 创建《斗破苍穹》适配包

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\create_adaptation_pack.py --pack-name dpcq_ch1_20 --source-title "斗破苍穹" --chapter-start 1 --chapter-end 20
```

### 执行《斗破苍穹》适配包

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20
```

### 校验最近一次《斗破苍穹》结果

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\validate_job_output.py --pack-name dpcq_ch1_20
```

## 8. 自定义 Python 路径

如果你不想使用默认虚拟环境位置，可以设置：

```powershell
$env:AI_MANGA_FACTORY_PYTHON="D:\custom-env\Scripts\python.exe"
```

`start.bat`、`start.sh` 和 `run_backend.ps1` 都会优先用这个变量。

## 9. 章节工厂新流程

现在默认流程已经升级为“章节工厂”：

- 每章都生成独立目录：`chapters/chapter_XX/`
- 每章都输出：
  - `storyboard/storyboard.json`
  - `storyboard/storyboard.csv`
  - `storyboard/storyboard.xlsx`
  - `audio/audio_plan.json`
  - `audio/voiceover.mp3`
  - `audio/ambience.wav`
  - `preview/chapter_preview.mp4`
  - `delivery/chapter_final_cut.mp4`
  - `qa/qa_report.md`
  - `qa/qa_snapshot.json`
- 整包层仍会生成：
  - `preview/preview.mp4`
  - `delivery/final_cut.mp4`
  - `qa_overview.md`
  - `chapters_index.json`

## 10. 新参数

`run_adaptation_pack.py` 现在支持：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-keyframe-count 3 --chapter-shot-count 10
```

可用参数：

- `--chapter-keyframe-count`
  - 每章生成多少张关键帧图片，建议 `3-4`
- `--chapter-shot-count`
  - 每章分镜表镜头数，建议 `10`
- `--use-model-storyboard`
  - 是否启用文本模型逐章细化镜头表

## 11. QA 门禁

现在 QA 不是“文件存在就算过”，而是章节级门禁：

- 每章 QA 没过，整包不会记为完成
- QA 会按四个硬指标检查：
  - 还原度
  - 叙事节奏
  - 制作水平
  - 改编合理性
- 共同约束见：
  - `E:\work\project-manager\workhome\projects\ai-manga-factory\agents\QUALITY_CONSTITUTION.md`

## 12. 单章返工与整包重建

当整包任务因为少量章节 QA 未通过而失败时，先走“单章返工 -> 整包重建”，不要默认整包重跑。

### 12.1 定向重跑失败章节

只重跑第 13 章：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 13 --chapter-end 13 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard
```

只重跑第 19 章：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 19 --chapter-end 19 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard
```

### 12.2 用返工章节重建整包

假设整包是 `job_12`，第 13 章返工结果是 `job_13`，第 19 章返工结果是 `job_14`：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\finalize_chapter_job.py --job-id 12 --replace-chapter 13=13 --replace-chapter 19=14
```

这个脚本会自动：

- 替换指定章节目录
- 重建 `chapters_index.json`
- 重建 `qa_overview.md`
- 重建 `prompts.json`
- 重建 `preview/preview.mp4`
- 重建 `delivery/final_cut.mp4`
- 重建 `manifest.json`
- 更新任务状态并重新沉淀 `result_summary.md` 和 `validation_report.md`

### 12.3 重跑校验

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\validate_job_output.py --job-id 12
```

## 13. Windows 一键跑包

如果你不想先打开后端页面，只想直接批量跑适配包并自动校验，用：

```bat
cd E:\work\project-manager\workhome\projects\ai-manga-factory
.\run_pack.bat dpcq_ch1_20 20 placeholder
```

真图模式：

```bat
cd E:\work\project-manager\workhome\projects\ai-manga-factory
.\run_pack.bat dpcq_ch1_20 20 real
```

`run_pack.bat` 会自动执行：

- `scripts\run_adaptation_pack.py`
- `scripts\validate_job_output.py`
