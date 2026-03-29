# data

项目内 `data/` 现在只承担两类职责：

- `reference/`：可版本化的静态参考数据
- 文档说明：告诉协作者哪些数据已经迁到独立运行时目录

测试截图、前端 smoke 报告、浏览器验收文档和临时验证视频不再放在业务项目目录。
默认验证输出已迁到：
- `E:\work\project-manager\workhome\management\ai-manga-factory\verification`

运行时数据已经从仓库内拆出，默认落到：

- `C:\Users\Administrator\OneDrive\CodexRuntime\ai-manga-factory`

如果你改了 `AI_MANGA_FACTORY_RUNTIME_DIR` 或 `secrets/runtime_storage_config.json`，实际运行时目录会跟着变。

当前运行时目录里通常会有：

- `artifacts/`
- `provider_usage/`
- `requirements/`
- `source_sessions/`
- `platform.db`
- `backend.log`
- `backend-error.log`

详细说明见：

- `docs/运行时数据区与云存储.md`
