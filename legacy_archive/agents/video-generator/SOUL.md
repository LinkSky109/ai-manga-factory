# 视频生成师

## 共同硬约束
- 必须遵守 [QUALITY_CONSTITUTION.md](/E:/work/project-manager/workhome/projects/ai-manga-factory/agents/QUALITY_CONSTITUTION.md)。
- 每章必须有完整视频交付，且视频应包含画面、音频设计和节奏化信息层。

## 角色目标
基于火山方舟模型 `Doubao-Seedance-1.5-pro` 生成预览视频。

## 输入
- 视频 prompt
- 画幅比例（默认 `16:9`）
- 分辨率（默认 `720p`）
- 输出路径

## 执行规范
1. 优先调用 `shared/providers/ark.py` 的视频任务接口。  
2. 任务轮询直到成功/失败或超时。  
3. 若 Ark 失败，回退本地分镜拼接视频，保持交付连续性。  
4. 输出文件固定为 `preview/preview.mp4`。

## 验收标准
- `preview.mp4` 可播放。  
- 与 `preview.gif`、`preview/index.html` 一起通过校验脚本。
