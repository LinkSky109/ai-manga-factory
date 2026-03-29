# Feature Requests

用于记录暂未落地但值得保留的新能力、自动化需求或长期工作方式。

## [FEAT-20260319-001] promote-seedance-2-0-when-ga

**Logged**: 2026-03-19T18:05:00+08:00  
**Priority**: high  
**Status**: pending  
**Area**: provider-routing

### Requested Capability
当 `Doubao-Seedance-2.0` 官方 API 正式上线后，把它提升为 AI 漫剧工厂的视频主模型。

### User Context
用户已经明确补充：目前先不误切，但 `Doubao-Seedance-2.0` 一旦正式上线，就应该替换当前的 `doubao-seedance-1-5-pro-251215` 成为视频主模型。

### Suggested Shape
- 当前阶段保持 `doubao-seedance-1-5-pro-251215` 为默认视频模型
- 持续关注火山官方 API 文档与模型 ID
- 一旦 `Doubao-Seedance-2.0` 进入正式 API 可调用状态，更新：
  - `shared/providers/ark.py`
  - `shared/providers/model_usage.py`
  - `data/provider_usage/model_budget_config.json`
  - 阶段模型方案文档
