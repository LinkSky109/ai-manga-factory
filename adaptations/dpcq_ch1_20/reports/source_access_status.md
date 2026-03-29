# 原文接入状态

- 时间：2026-03-19T12:20:00+08:00
- 适配包：`dpcq_ch1_20`
- 当前状态：原文接入入口已就绪，尚未导入《斗破苍穹》前 20 章的合法正文

## 已完成

- 已为适配包建立 `source/chapters/` 原文目录
- 已补 `source_urls.template.json`
- 已补 `request_headers.template.json`
- 已补 `request_cookies.template.json`
- 已补 `playwright_capture.template.json`
- 已实现 `collect_source_text.py`
- 已实现 `playwright_source_capture.py`
- 已实现 `build_source_url_manifest.py`
- 已实现 `run_source_ingestion_pipeline.py`
- 已把 `source_urls.json` 升级为稳定结构：`title`、`catalog_title`、`match_aliases`、`match_keywords`

## 已验证

- 本地逐章 HTML 导入已实测通过
- 原文导入后的摘要生成链已实测通过
- Playwright 本地最小抓取闭环已实测通过：`capture -> playwright_html -> collect_source_text`
- 保存目录页 HTML 后自动生成 `source_urls.json` 已实测通过
- 一键流水线已具备闭环能力：目录页解析 -> 抓取 -> 导入 -> 摘要生成

## 当前卡点

- 匿名访问起点等官方阅读页会返回 `202 + probe.js` 校验壳，不是正文
- 真实浏览器自动化上下文当前也会先落到腾讯滑块验证码，不是目录页 DOM
- 当前工作区内还没有《斗破苍穹》前 20 章的合法原文文件、目录页 HTML 和登录态
- 运行中的系统 Edge 占用了默认用户资料，暂时无法直接用 Playwright 持久化复用该资料导出状态

## 下一步

任选一种方式继续：

1. 提供你自己的正版目录页 HTML 和登录态，然后直接跑 `run_source_ingestion_pipeline.py`
2. 提供浏览器保存下来的逐章 HTML，然后用 `collect_source_text.py --source-dir` 导入
3. 提供你已整理好的逐章 txt/md/json，再走原文导入链
4. 你手动过一次起点滑块验证码和登录，我继续把目录页 HTML 与状态导出回项目目录

## 最新进展（2026-03-19）

- 已通过微信扫码登录起点，并复用真实 Edge 会话接管目录页
- 已导出正版目录页 HTML：
  - `adaptations/dpcq_ch1_20/source/incoming/qidian_catalog_live.html`
- 已导出会话状态与 Cookie：
  - `data/source_sessions/dpcq_ch1_20/manual_browser/qidian_catalog_live_storage_state.json`
  - `adaptations/dpcq_ch1_20/source/incoming/request_cookies.json`
- 已生成并核对前 20 章 URL 清单：
  - `adaptations/dpcq_ch1_20/source/incoming/source_urls.json`
- 已通过真实浏览器 CDP 顺序抓取前 20 章正文 HTML：
  - `adaptations/dpcq_ch1_20/source/incoming/manual_browser_html/`
- 已导入前 20 章原文并落盘：
  - `adaptations/dpcq_ch1_20/source/chapters/`
  - `adaptations/dpcq_ch1_20/source/source_manifest.json`
- 已基于原文重生成 `chapter_briefs.json`

## 当前结论

- 《斗破苍穹》前 20 章的正版目录页、登录态、章节 URL、逐章原文和原文驱动摘要链路已经打通
- 对起点这类站点，当前最稳路径不是“导出 storage state 后换新 Playwright 浏览器批量抓”，而是“人工扫码登录 -> CDP 附着真实会话 -> 顺序抓章 -> 导入原文”
