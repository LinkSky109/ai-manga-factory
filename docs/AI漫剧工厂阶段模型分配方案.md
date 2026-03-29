# AI 漫剧工厂阶段模型分配方案

这份方案对应当前代码基线，不是空泛建议。

## 当前生产阶段

| 阶段 | 当前入口 | 当前默认模型 | 降级规则 | 性价比判断 | Coding Plan Pro |
| --- | --- | --- | --- | --- | --- |
| 原文接入 | `collect_source_text.py`、`playwright_source_capture.py`、`capture_cdp_chapters.py` | 不用内容模型 | 无 | 最高 | 很适合做脚本与自动化 |
| 章节摘要生成 | `generate_chapter_briefs.py` | `doubao-seed-2-0-lite-260215` | `2.0 mini` -> `1.6 251015` -> `1.6` -> `1.6 flash` | 高 | 不建议代替内容模型 |
| 模型分镜精修 | `chapter_factory.py::_generate_storyboard` | `doubao-seed-2-0-pro-260215` | `2.0 lite` -> `2.0 mini` -> `1.6 251015` -> `1.6` -> `1.6 flash` | 中高 | 不建议代替内容模型 |
| 主角色图 | `chapter_factory.py::_write_lead_character` | `doubao-seedream-5-0-260128` | `5.0 lite` -> `4.5 251128` -> `Doubao-Seedream-4.5` -> `4.0` | 中 | 不适用 |
| 章节关键帧 | `chapter_factory.py::_generate_keyframes` | `doubao-seedream-5-0-lite-260128` | `4.5 251128` -> `Doubao-Seedream-4.5` -> `4.0` | 高 | 不适用 |
| 章节视频 / 整包视频 | `chapter_factory.py::_render_chapter_video`、`_concat_videos` | 本地合成 | 无 | 高 | 不适用 |
| 未来外部视频生成 | `ark.py::generate_video_to_file` | `doubao-seedance-1-5-pro-251215` | `1.0 pro` -> `Doubao-Seedance-1.5-pro` | 待验证 | 不适用 |
| 工厂研发与脚本维护 | `scripts/`、`backend/`、`frontend/` | `Coding Plan Pro` | 无 | 最高 | 最适合 |

## 当前代码已经落地的变化

当前代码已经按这份方案做了分阶段默认值：

- 章节摘要默认用 `doubao-seed-2-0-lite-260215`
- 模型分镜默认用 `doubao-seed-2-0-pro-260215`
- 主角色图默认用 `doubao-seedream-5-0-260128`
- 章节关键帧默认用 `doubao-seedream-5-0-lite-260128`

对应代码位置：

- `E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\generate_chapter_briefs.py`
- `E:\work\project-manager\workhome\projects\ai-manga-factory\modules\manga\chapter_factory.py`
- `E:\work\project-manager\workhome\projects\ai-manga-factory\shared\providers\ark.py`

## 降级规则

统一规则：

1. 先按当前阶段请求的主模型执行。
2. 如果本地预算账本判断即将超阈值，或者模型返回额度不足、欠费、限流、不可用错误，则自动切到下一个备选模型。
3. 文本按估算 token 记账，图片和视频按调用次数记账。
4. `warning_ratio=0.8` 时前端预警，`switch_ratio=0.9` 时优先切换。

## 为什么这样分

### 章节摘要
这是全书里最高频、最大批量的文本任务。用 `2.0 Lite` 最划算。

### 模型分镜
这一步更吃推理和一致性，尤其要守角色动机、名场面、世界观规则，所以默认升到 `2.0 Pro`。

### 主角色图
这类图是整包视觉基准，不适合省。

### 章节关键帧
这是批量最大的一层图像成本，默认用 `5.0 Lite` 更合适。

### 视频
当前主链还是本地合成，所以视频模型不是现阶段成本瓶颈。先别误以为“开了视频模型套餐就已经在用”。

## Coding Plan Pro 怎么用最值

`Coding Plan Pro` 最适合：

- 写抓取脚本
- 写解析器
- 修原文导入链
- 改前端监控面板
- 接入新模型 API
- 写批处理和自动化脚本
- 做代码级 QA 和回归修改

`Coding Plan Pro` 不适合直接替代：

- 小说章节摘要主模型
- 模型分镜主模型
- 图像生成主模型

## 未来升级规则

用户已经明确要求：

- 一旦 `Doubao-Seedance-2.0` 官方 API 正式上线，就把它提升为视频主模型。

在那之前：

- 继续保留 `doubao-seedance-1-5-pro-251215` 为当前视频 API 主模型
- 保留 `doubao-seedance-1-0-pro-250528` 为后备
