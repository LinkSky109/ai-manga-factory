# Playwright 正版原文抓取

这份文档说明如何把需要登录的正版小说阅读站接进 AI 漫剧工厂，尤其是起点中文网这类有验证码、登录态和动态页面的站点。

## 适用场景

- 目录页或正文页只有登录后才能访问
- 匿名请求只能拿到验证码壳页，不是正文
- 你希望把正版目录页、章节 HTML、Cookie 和原文摘要链路接到项目里

## 推荐路径

优先顺序：

1. 真实浏览器手动登录
2. 导出目录页 HTML、Cookie、storage state
3. 生成 `source_urls.json`
4. 在同一个真实浏览器会话里顺序抓章节
5. 导入 `source/chapters`
6. 重生成 `chapter_briefs.json`

原因：

- 把登录态搬进一个全新的 Playwright 上下文，对起点这类站点更容易在第 2 章以后退化成验证码壳页
- 复用用户刚刚通过验证码的真实浏览器会话，稳定性更高

## 第一步：准备登录态

如果只是普通登录页，可以先用：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\playwright_source_capture.py login --pack-name dpcq_ch1_20 --config-file .\adaptations\dpcq_ch1_20\source\playwright_capture.template.json
```

如果目标是起点中文网，且你平时通过微信扫码登录，推荐直接走“真实浏览器 + CDP”路线。

## 起点微信扫码推荐路径

### 1. 打开真实 Edge 会话

确保 Edge 用独立资料目录启动，并带远程调试端口。然后打开目录页，在该窗口里手动完成微信扫码登录。

### 2. 导出目录页与会话

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\capture_manual_browser_session.py --pack-name dpcq_ch1_20 --cdp-url http://127.0.0.1:9333 --target-url https://www.qidian.com/book/1209977/catalog/ --url-contains /book/1209977/ --title-contains 斗破苍穹 --label qidian_catalog_live
```

这一步会沉淀：

- `adaptations/dpcq_ch1_20/source/incoming/qidian_catalog_live.html`
- `adaptations/dpcq_ch1_20/source/incoming/request_cookies.json`
- `data/source_sessions/dpcq_ch1_20/manual_browser/qidian_catalog_live_storage_state.json`

### 3. 从目录页生成章节 URL 清单

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\build_source_url_manifest.py --pack-name dpcq_ch1_20 --toc-file .\adaptations\dpcq_ch1_20\source\incoming\qidian_catalog_live.html --base-url https://www.qidian.com --chapter-start 1 --chapter-end 20 --force
```

生成结果：

- `adaptations/dpcq_ch1_20/source/incoming/source_urls.json`

### 4. 在同一个真实浏览器会话里顺序抓章

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\capture_cdp_chapters.py --pack-name dpcq_ch1_20 --cdp-url http://127.0.0.1:9333 --url-manifest .\adaptations\dpcq_ch1_20\source\incoming\source_urls.json --output-dir .\adaptations\dpcq_ch1_20\source\incoming\manual_browser_html --capture-manifest .\adaptations\dpcq_ch1_20\source\incoming\manual_browser_capture_manifest.json --report-path .\adaptations\dpcq_ch1_20\reports\manual_browser_capture_report.md --chapter-start 1 --chapter-end 20 --wait-for-timeout-ms 2500 --delay-ms 1500
```

这一步会把前 20 章 HTML 落到：

- `adaptations/dpcq_ch1_20/source/incoming/manual_browser_html/`

## 导入原文

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\collect_source_text.py --pack-name dpcq_ch1_20 --source-dir .\adaptations\dpcq_ch1_20\source\incoming\manual_browser_html --chapter-start 1 --chapter-end 20 --overwrite
```

结果会落到：

- `adaptations/dpcq_ch1_20/source/chapters/`
- `adaptations/dpcq_ch1_20/source/source_manifest.json`

## 重生成章节摘要

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\generate_chapter_briefs.py --pack-name dpcq_ch1_20 --chapter-start 1 --chapter-end 20 --force
```

## 一键流水线适用范围

如果站点反爬不强、直接复用 Playwright 登录态就够，可以继续使用：

```powershell
cd E:\work\project-manager\workhome\projects\ai-manga-factory
E:\work\.venvs\ai-manga-factory\Scripts\python.exe .\scripts\run_source_ingestion_pipeline.py --pack-name dpcq_ch1_20 --toc-file E:\novels\dpcq_catalog.html --base-url https://www.qidian.com
```

但对起点这类强 WAF 站点，优先使用本页这条“真实浏览器 + CDP 顺序抓章”路线。
