# reports

这里保存自动沉淀出来的结果：

- `stage_report.md`：最近一次整包执行的阶段报告
- `latest_result_pointer.json`：共享报告当前绑定的 job 指针
- `latest_result.md`：最近一次结果摘要共享副本
- `latest_validation.md`：最近一次校验报告共享副本
- `result_journal.md`：所有 job 的沉淀索引
- `job_<id>_summary.md`：单次 job 的结果摘要
- `job_<id>_validation.md`：单次 job 的校验报告

使用约定：

- 管理同步和 QA 复核优先查看 `data/artifacts/job_<id>/...`。
- `latest_result.md` / `latest_validation.md` 只用于便捷浏览，必须先通过 `latest_result_pointer.json` 或明确的 `job_id` 绑定后再引用。
