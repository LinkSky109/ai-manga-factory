# 产物归档与预览服务

## 目标

Step 6 把预览从占位卡片升级为真实文件服务：

- job 完成后自动在 `artifact_root` 写入产物文件
- 自动写入多目标归档并建立索引
- 在 `preview_root` 生成可直接访问的预览资源
- 通过 `/api/v1/previews/artifacts/{id}` 提供统一访问入口

## 当前实现

- 产物模型：[apps/api/src/infrastructure/db/models/artifact.py](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/db/models/artifact.py)
- 存储服务：[apps/api/src/infrastructure/storage/artifact_storage.py](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/storage/artifact_storage.py)
- 归档同步 runner：[apps/api/src/application/services/archive_sync_runner.py](/Users/link/work/ai-manga-factory/apps/api/src/application/services/archive_sync_runner.py)
- 预览查询：[apps/api/src/application/queries/preview.py](/Users/link/work/ai-manga-factory/apps/api/src/application/queries/preview.py)
- 预览路由：[apps/api/src/api/routes/previews.py](/Users/link/work/ai-manga-factory/apps/api/src/api/routes/previews.py)
- Artifact 查询与补同步路由：[apps/api/src/api/routes/assets.py](/Users/link/work/ai-manga-factory/apps/api/src/api/routes/assets.py)
- Storage target 路由：[apps/api/src/api/routes/storage.py](/Users/link/work/ai-manga-factory/apps/api/src/api/routes/storage.py)
- 归档 adapter：[apps/api/src/infrastructure/storage/archive_adapters.py](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/storage/archive_adapters.py)
- 归档索引：[apps/api/src/infrastructure/storage/archive_index.py](/Users/link/work/ai-manga-factory/apps/api/src/infrastructure/storage/archive_index.py)

## 文件落点

- 源产物：`ARTIFACT_ROOT/project_<id>/chapter_<id>/job_<id>/...`
- 预览文件：`PREVIEW_ROOT/project_<id>/chapter_<id>/job_<id>/...`
- 本地归档：`ARCHIVE_ROOT/local-archive/project_<id>/chapter_<id>/job_<id>/...`
- 对象存储镜像：`OBJECT_STORAGE_ROOT/<bucket>/project_<id>/chapter_<id>/job_<id>/...`
- 归档索引：`ARCHIVE_INDEX_PATH`
- 归档补同步重试上限：`ARCHIVE_SYNC_MAX_ATTEMPTS`

## 归档目标

当前支持的 adapter：

- `local-archive`
- `object-storage`
- `quark-pan`
- `aliyundrive`

由 `ARCHIVE_TARGETS` 控制启用顺序，例如：

```bash
ARCHIVE_TARGETS=local-archive,object-storage
```

当前 `object-storage`、`quark-pan`、`aliyundrive` 都是面向远端语义设计的 mirror adapter：

- `object-storage` 生成 bucket/key 结构和 `s3://...` URL 语义
- `quark-pan` 生成 `quark://...` URL 语义
- `aliyundrive` 生成 `aliyundrive://...` URL 语义

后续接入真实 OSS / S3 / 网盘 SDK 时，可保持业务层和索引结构不变，只替换 adapter 的写入实现。

`object-storage` 现在额外支持 `OBJECT_STORAGE_MODE=s3`：

- `mirror`：写入本地镜像目录，并生成 `s3://bucket/key` 语义 URL
- `s3`：通过 S3 兼容上传器直接推送到远端 bucket，不落本地镜像副本
- S3 模式依赖 `S3_ENDPOINT`、`S3_BUCKET`、`S3_ACCESS_KEY_ID`、`S3_SECRET_ACCESS_KEY`

`quark-pan` 与 `aliyundrive` 现在额外支持 `api` 模式：

- `QUARK_PAN_MODE=api`：通过 Quark SDK 直接上传，不再写 mirror 副本
- `ALIYUNDRIVE_MODE=api`：通过 Aligo 直接上传，不再写 mirror 副本
- Quark API 模式依赖 `AI_MANGA_FACTORY_QUARK_COOKIE` 或 `QUARK_PAN_COOKIE_FILE`
- AliyunDrive API 模式依赖 `ALIYUNDRIVE_CONFIG_DIR` 下已有登录态
- API 模式的登录准备通过 [auth_remote_storage.py](/Users/link/work/ai-manga-factory/scripts/auth_remote_storage.py) 完成

建议流程：

```bash
cd /Users/link/work/ai-manga-factory
python3 scripts/auth_remote_storage.py --provider quark-pan --prepare-qr
python3 scripts/auth_remote_storage.py --provider quark-pan
python3 scripts/auth_remote_storage.py --provider aliyundrive
```

运行原则：

- API / worker 只消费已存在的 secrets、cookie、SDK config
- 交互式登录只在认证脚本里进行，不在服务启动链路里进行
- `GET /api/v1/storage/targets` 会直接反映当前凭证 readiness

## Ark 供应商接入

- 当配置了 `ARK_API_KEY` 后，系统会自动注册 `ark-story`、`ark-video` 与 `ark-image` 三个 provider
- `ark-story` 优先用于 `llm` 分镜节点，生成真实文本内容后再包装为 HTML 预览
- `ark-video` 优先用于 `video` 节点，直接产出 `video/mp4` 预览资源
- `ark-image` 优先用于 `image` 节点，直接产出 `image/png` 预览资源
- 若 Ark 运行时失败，系统会回退到当前优先级链里的下一家供应商，例如 `llm-story` 或 `vidu-primary`
- 每个 step 的 `output_snapshot` 会记录 `provider_candidates`、`provider_attempts` 与 `resolved_provider_key`
- 前端监控台会直接展示最近命中路径、fallback 历史和最终失败节点

## 当前 API

- `GET /api/v1/projects/{project_id}/previews`
- `POST /api/v1/projects/{project_id}/artifacts/archives/sync`
- `GET /api/v1/previews/artifacts/{artifact_id}`
- `GET /api/v1/assets/artifacts?project_id=<id>`
- `GET /api/v1/assets/artifacts/{artifact_id}`
- `POST /api/v1/assets/artifacts/{artifact_id}/archives/sync`
- `GET /api/v1/assets/artifacts/{artifact_id}/archive-sync-runs`
- `POST /api/v1/assets/artifacts/{artifact_id}/archive-sync-runs`
- `GET /api/v1/storage/targets`

`GET /api/v1/storage/targets` 当前会返回：

- `archive_type`
- `mode`
- `location`
- `remote_base_url`
- `is_ready`
- `readiness_reason`

其中 Quark / AliyunDrive 在 `api` 模式下会把 readiness 绑定到真实凭证状态：

- Quark：SDK 依赖 + cookie 是否存在
- AliyunDrive：SDK 依赖 + config 目录是否已有登录态文件

## 资源类型

- `llm`：生成 HTML 预览页
- `video`：默认生成 HTML 预览页；命中 `ark-video` 时生成真实 `video/mp4`
- `image`：默认生成 SVG 预览；命中 `ark-image` 时生成真实 `image/png`
- `voice`：生成可直接播放的 WAV 音频
- 其他节点：默认生成 HTML 预览页

## 归档同步队列

- `artifact_sync_runs` 记录归档补同步任务，状态流转为 `queued -> running -> completed/failed`
- `POST /api/v1/assets/artifacts/{artifact_id}/archive-sync-runs` 用于按目标类型入队，例如 `object-storage`
- `GET /api/v1/assets/artifacts/{artifact_id}` 现在会直接返回 `sync_runs`，便于控制塔汇总展示最新补同步状态
- `apps/worker` 现在会在消费完 async job 后继续轮询归档同步队列
- 当前适合处理“已有 artifact 需要补推远端归档”的场景，不影响主 job 执行链
- 若目标未启用，API 会返回 `400`
- 失败任务会在 `ARCHIVE_SYNC_MAX_ATTEMPTS` 上限内自动重新排队，超限后落为 `failed`

## 校验和

- `artifacts.artifact_metadata.checksum_sha256` 保存源产物的 SHA-256
- `artifact_archives.checksum_sha256` 保存每个归档副本对应的校验和
- manifest 索引也会写入 `checksum_sha256`

## 下一步增强

- 接入真实对象存储 / 网盘 SDK
- 为视频节点生成真实 MP4/HLS 资源
- 把更多 provider 路由明细沉淀到监控报表与告警规则
