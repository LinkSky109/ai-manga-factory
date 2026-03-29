# Backend 快速说明

## 启动

先准备虚拟环境和依赖：

```powershell
python -m venv E:\work\.venvs\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe -m pip install -r requirements.txt
```

启动 API：

```powershell
E:\work\.venvs\ai-manga-factory\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

或直接使用根目录包装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File E:\work\project-manager\workhome\projects\ai-manga-factory\run_backend.ps1
```

## HTTP 接口

- `GET /`
  - 如果 `web/dist/` 已构建，返回新版前端
  - 否则回退到旧版前端
- `GET /legacy`
  - 返回旧版单文件控制台
- `GET /health`
- `GET /capabilities`
- `GET /projects`
- `POST /projects`
- `GET /jobs`
- `GET /jobs/{id}`
- `POST /jobs`
- `GET /adaptation-packs`
- `GET /adaptation-packs/{pack_name}/latest-result`
- `POST /adaptation-packs/{pack_name}/jobs`
- `POST /adaptation-packs/{pack_name}/batches`
- `GET /provider-usage`
- `GET /model-stage-plan`
- `GET /runtime-storage`
- `GET /artifacts/...`
- `GET /adaptation-files/...`

## 结果沉淀

每个 job 在完成或失败后，都会自动补充这些文件：

- `data/artifacts/job_<id>/result_summary.md`
- `data/artifacts/job_<id>/validation_report.md`
- `data/artifacts/job_<id>/result_snapshot.json`

如果 job 绑定了适配包，还会同步写入：

- `adaptations/<pack_name>/reports/job_<id>_summary.md`
- `adaptations/<pack_name>/reports/job_<id>_validation.md`
- `adaptations/<pack_name>/reports/latest_result_pointer.json`
- `adaptations/<pack_name>/reports/latest_result.md`
- `adaptations/<pack_name>/reports/latest_validation.md`
- `adaptations/<pack_name>/reports/result_journal.md`

说明：

- `data/artifacts/job_<id>/...` 是权威 job 级证据。
- `latest_result_pointer.json` 记录共享报告当前绑定到哪个 job。
- `latest_result.md` / `latest_validation.md` 只是便捷共享副本，不应脱离 `job_id` 单独作为管理同步依据。
