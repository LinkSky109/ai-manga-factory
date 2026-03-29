# AI 漫剧工厂使用说明

## 1. 定位

AI 漫剧工厂是业务生产平台，用来执行“小说章节 -> 漫剧任务 -> 图片/视频产物 -> 结果沉淀”。

当前项目目录只保留：

- 业务代码
- 业务脚本
- 适配包输入
- 业务产物
- 自动沉淀文档
- 业务侧智能体配置

多智能体并行研发方案已经迁到外部方法层：

- `E:\work\project-manager\MULTI_AGENT_DEV_PLAN.md`

## 2. 启动

在项目根目录执行：

```powershell
python -m venv E:\work\.venvs\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe -m pip install -r requirements.txt
.\start.bat
```

如果你在 bash 环境中运行：

```bash
cd /e/work/project-manager/workhome/projects/ai-manga-factory
./start.sh
```

浏览器打开：

- `http://127.0.0.1:8000`

## 3. 页面怎么用

### 创建通用任务

1. 选择能力
2. 填项目名
3. 填输入参数
4. 点击“创建并执行”

### 用适配包跑整包

1. 选择适配包
2. 填项目名
3. 设置分镜图数量
4. 点击“运行整包”或“整包真图模式”

### 用适配包分批跑

1. 选择适配包
2. 设置每批章节数
3. 点击“分批运行”或“分批真图模式”

## 4. 自动沉淀在哪里

每个 job 完成或失败后，都会自动生成：

- `data/artifacts/job_<job_id>/result_summary.md`
- `data/artifacts/job_<job_id>/validation_report.md`
- `data/artifacts/job_<job_id>/result_snapshot.json`
- `data/artifacts/job_<job_id>/preview/preview.mp4`
- `data/artifacts/job_<job_id>/delivery/final_cut.mp4`

如果任务绑定了适配包，还会同步写入：

- `adaptations/<pack_name>/reports/latest_result.md`
- `adaptations/<pack_name>/reports/latest_validation.md`
- `adaptations/<pack_name>/reports/result_journal.md`

## 5. 如何新建一个小说适配包

例如要做《斗破苍穹》前 20 章：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\create_adaptation_pack.py --pack-name dpcq_ch1_20 --source-title "斗破苍穹" --chapter-start 1 --chapter-end 20
```

然后补充：

- `adaptations/dpcq_ch1_20/chapter_briefs.json`

如果希望直接调用模型自动生成摘要，可以执行：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\generate_chapter_briefs.py --pack-name dpcq_ch1_20
```

最后执行：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --scene-count 20
```

## 6. 相关说明

- 本项目说明：
  - `E:\work\project-manager\workhome\projects\ai-manga-factory\README.md`
- 并行研发方法说明：
  - `E:\work\project-manager\workhome\management\ai-manga-factory\multi-agent-guide-zh.md`

## 7. 章节工厂模式

当前默认不是“整单出一份总视频”，而是“每章单独交付，再聚合整包”：

- 每章都有自己的分镜表、音频方案、预览视频、交付视频和 QA 报告
- 整包再聚合为总预览视频和总交付视频
- 这样可以逐章返工、逐章审片，不会因为一个大包太粗而看不出问题

推荐命令：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-keyframe-count 3 --chapter-shot-count 10
```

如果要启用真图：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images
```

如果要让模型逐章细化分镜：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-keyframe-count 3 --chapter-shot-count 10 --use-model-storyboard
```

## 8. 局部返工与整包重建

如果整包任务只坏了少数章节，推荐按下面的顺序处理：

1. 先定向重跑失败章节
2. 再把返工章节回填到原整包任务
3. 最后重建总预览、总交付和总校验

示例：重跑第 13 章

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 13 --chapter-end 13 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard
```

示例：重跑第 19 章

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\run_adaptation_pack.py --pack-name dpcq_ch1_20 --chapter-start 19 --chapter-end 19 --chapter-keyframe-count 3 --chapter-shot-count 10 --real-images --use-model-storyboard
```

示例：把返工章节回填到原整包 `job_12`

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\finalize_chapter_job.py --job-id 12 --replace-chapter 13=13 --replace-chapter 19=14
```

回填后重新校验：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe scripts\validate_job_output.py --job-id 12
```

现在校验器已经支持真实章节号，不会再把 `chapter_13`、`chapter_19` 这类定向返工任务误判成 `chapter_01` 缺失。
## 章节产物 JSON 查看顺序

启用适配包资产锁时，推荐按下面顺序查看章节产物：

1. `story_grounding.json`
   - 章节事实源
   - 角色、场景、世界规则、候选台词与有效旁白候选
2. `storyboard_blueprint.json`
   - 目标时长、镜头数、关键帧数
   - 每个 shot 的 `speaker`、`present_characters`、`dialogue`、`narration`
3. `storyboard.json`
   - 最终分镜表
   - `对白角色`、`出镜角色` 应该已经全部归一成真实角色名
4. `audio_plan.json`
   - `dialogue_tracks` / `narration_tracks` / `voice_tracks`
   - `canonical_character`、`voice_id`、`bus`、`priority`、`duck_target`
5. `manifest.json`
   - 顶层追踪信息
   - `asset_lock`、`asset_cards`、`story_pipeline`

## 标准化资产卡

pack 模式下，除了 `asset_lock.json`，还需要维护两类标准化资产卡：

- `assets/characters/character_cards.json`
- `assets/scenes/scene_cards.json`

角色卡最少应包含：

- `name`
- `voice_id`
- `aliases`
- `fixed_prompt`
- `dramatic_role`
- `asset_status`
- `reference_assets`

场景卡最少应包含：

- `scene_id`
- `baseline_prompt`
- `asset_status`
- `reference_assets`

这些卡片文件的意义是把“角色/场景资产是否真的补齐”从图片占位变成结构化状态，而不是只靠 `reference_image_path` 存不存在来猜。

## 普通 job 与 asset_lock pack 的兼容差异

普通 job：

- 可以没有 `asset_lock.json`
- 仍允许走兼容模式出片
- 不会启用“真实角色必达”的硬门禁

asset_lock pack：

- 默认读取 `asset_lock.json`、角色卡、场景卡
- 分镜阶段必须直接产出真实角色名
- `audio_plan` 不再负责把槽位 speaker 兜底修正成真实角色
- QA 会检查未归一角色、无效资产路径、generic canonical fallback 等问题
## 2026-03-30 补充

### 1. 章节长度配置

适配包现在支持小说维度的章节长度规划：

- `pack.json.default_target_duration_seconds`
- `chapter_briefs.json[*].target_duration_seconds`

运行时会自动汇总为 `chapter_duration_plan`，供 `storyboard_blueprint.json` 与后续时长回流使用。

### 2. 可审阅资产卡

`character_cards.json` / `scene_cards.json` 现在除了基础识别字段，还要关注：

- `asset_status_detail`
- `review_status`
- `approval_notes`
- `owner`
- `review_checklist`
- `source_evidence`
- `last_verified_job_id`
- `usage_scope`

这让资产库可以直接做审阅，而不是只凭占位图判断。

### 3. 外部 runtime 结果路径

pack 验证结果不再回写 `adaptations/<pack>/reports/`，请改看：

- `C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory\artifacts\job_<id>`
- `C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory\artifacts\pack_reports\<pack>\reports`
