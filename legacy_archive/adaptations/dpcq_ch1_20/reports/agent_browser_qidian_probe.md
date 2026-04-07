# 起点浏览器探测报告

- 时间：2026-03-19T11:35:00+08:00
- 目标站点：`https://www.qidian.com/`
- 目标书目：`https://www.qidian.com/book/1209977/catalog/`
- 浏览器方式：`agent-browser` 真实浏览器自动化

## 本次结论

- 不是只有裸 HTTP 会触发拦截，真实浏览器自动化上下文也会先进入腾讯滑块验证码
- 当前拿到的是 WAF 验证页，不是《斗破苍穹》目录页 HTML
- 当前自动化会话里没有拿到起点账号登录态

## 已沉淀的现场文件

- 验证页 HTML：`adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.html`
- 验证页截图：`adaptations/dpcq_ch1_20/source/incoming/qidian_waf_gate.png`
- agent-browser state：`data/source_sessions/dpcq_ch1_20/agent_browser/qidian_waf_state.json`
- agent-browser cookies：`data/source_sessions/dpcq_ch1_20/agent_browser/qidian_waf_cookies.txt`

## 页面特征

- 页面实际返回腾讯验证码壳，包含 `TencentCaptcha` 脚本
- 当前验证码类型是滑块拼图，不是目录页 DOM
- 会话里可见 WAF 相关 Cookie，例如 `w_tsfp` 和 `x-waf-captcha-referer`

## 系统浏览器线索

- 这台机器的 Edge 默认资料有起点访问历史
- 但当前 Edge 默认资料正在被运行中的 Edge 占用
- 直接复用 `Edge User Data\\Default` 做 Playwright 持久化上下文时，浏览器会立即退出

## 当前阻塞点

- 需要人工完成一次腾讯滑块验证码
- 如果后续还要拿“账号登录态”，还需要人工在真实浏览器里完成起点登录

## 最短接力点

任选一种方式继续：

1. 你手动过一次滑块验证码和登录，我再继续导出目录页 HTML 与登录态
2. 你先关闭所有 Edge 窗口，我再尝试复用系统 Edge 默认资料直接导出状态
