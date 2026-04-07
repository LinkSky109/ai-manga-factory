# 道诡异仙适配包

- 适配包名：`dgyx_ch1_20`
- 原作：`道诡异仙`
- 章节范围：`1-20`
- 默认项目名：`dgyx-ch1-20`

## 文件说明

- `pack.json`：适配包元信息
- `chapter_briefs.json`：前 20 章的结构化章节摘要
- `reports/`：自动沉淀出来的阶段报告、校验报告和结果索引

## 运行方式

```powershell
E:\work\project-manager\workhome\projects\ai-manga-factory\.venv\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\run_adaptation_pack.py --pack-name dgyx_ch1_20 --scene-count 20
```

启用真图/真视频：

```powershell
$env:ARK_API_KEY="你的 key"
E:\work\project-manager\workhome\projects\ai-manga-factory\.venv\Scripts\python.exe E:\work\project-manager\workhome\projects\ai-manga-factory\scripts\run_adaptation_pack.py --pack-name dgyx_ch1_20 --scene-count 20 --real-images
```
