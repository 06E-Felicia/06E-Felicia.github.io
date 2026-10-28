# 第一轮 bug 修复说明

2026-10-22 按要求撤销后续自由优化，只保留第一次扫描时的 bug 修复。

## 已恢复

首页、预报页、预警页恢复原版 HTML 布局和样式，包括原背景图、卡片比例、导航外观、角色位置、公告及预警弹窗流程。后续增加的天气看板、配色方案、刷新按钮、常驻预警摘要、统一弹窗管理和桌面宽度改版均已移除。

## 保留的修复

| 问题 | 修复方式 |
| --- | --- |
| 首页刷新失败会用默认配置覆盖已经加载的天气和预警 | 失败时保留上次成功数据；首次加载失败显示提示；恢复联网或返回页面时重新读取 |
| 天气请求可能一直挂起，缺失预警字段被当作无预警 | 共用 `weather-data.js`，检查 HTTP、JSON 和必需字段，设置 15 秒超时；合法空数组与读取失败分开处理 |
| 预报、预警页的 StormSim 菜单无法正常操作 | 从原首页提取 `navigation.js`，三个天气页面共用原有菜单逻辑，支持鼠标、触屏和键盘 |
| 航班状态检查和外层逻辑重复读取快照 | 修正状态检查的调用方式，首次加载、手动刷新、机场切换及新快照轮询各读取一次 |
| Flightdat 页面可能漏掉第一份可用快照 | 状态轮询允许从尚无数据切换为第一份成功快照 |
| 隐藏页面继续发出常规轮询请求 | 暂停隐藏页面的数据轮询，返回后立即检查；首页保留请求并发保护，Flightdat 手动刷新按钮防止重复点击 |
| 首页没有天气图标时使用空图片地址 | 隐藏空图标并移除空 `src` |

天气页面仅增加读取失败提示所需的元素和样式，以及修复脚本的引用和缓存版本号，没有保留后续视觉调整。Feimadat 的同类请求修复仍保留，暂停入口维持原状。

## 验证

```bash
node development/tests/test_weather_data.cjs
node development/tests/test_alerts.cjs
TEST_BROWSER_CHANNEL=chrome node development/tests/test_refresh_browser.cjs
TEST_BROWSER_CHANNEL=chrome node development/tests/test_ui.cjs
TEST_BROWSER_CHANNEL=chrome node development/tests/test_browser.cjs
node development/tests/test_flightdata_browser.cjs
node development/tests/test_feimadat_browser.cjs
git diff --check
```

浏览器用例需要 Playwright 和本机 Chrome，使用本地或隔离快照，不触发线上采集。原有弹窗测试保留第一轮的断言修正：公告正文中的 Sol 链接是 Tab 循环的首个链接。
