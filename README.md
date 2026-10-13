# 06E-Felicia's Weather Board

Static weather dashboard for Shenzhen Middle School Meteorology Club.

The page itself is static (`index.html` + assets), while weather data is updated by Python scripts under `auto_update/` that write into `config.json`.

## Highlights

- Static front-end, easy to host on GitHub Pages.
- Config-driven runtime data in `config.json`.
- Official Shenzhen Meteorological Bureau data updater:
	- `auto_update/updater.py`: updates all weather blocks in one run.
	- `auto_update/utils/util_updater.py`: reads the public data files used by `weather.sz.gov.cn` for live observations, a seven-day forecast, and active alerts.
- Dedicated `forecast.html` and `warnings.html` pages, populated from the same update.
- Unified error logging to `logs/run.log` when fetch/update actions fail.

## Project Structure

```text
.
|- index.html
|- forecast.html
|- warnings.html
|- config.json
|- README.md
|- assets/
|  |- scripts/script.js
|  |- scripts/forecast.js
|  |- scripts/warnings.js
|  |- styles/style.css
|  `- images/
|- auto_update/
|  |- updater.py
|  `- utils/
|     |- __init__.py
|     |- util_services.py
|     `- util_updater.py
|- logs/
`- .github/workflows/update.yml
```

## How It Works

1. Front-end loads `config.json` on page load.
2. The browser scripts read:
	 - `LIVE_DATA`
	 - `MANUAL_CONFIG`
	 - `ALERT_CONFIG`
 	 - `FORECAST`
 	 - `WARNINGS`
3. `auto_update/updater.py` fetches the public official data files used by the Shenzhen Meteorological Bureau website.
4. It writes live observations, the homepage forecast, seven forecast days, and active Shenzhen warnings into `config.json`.
5. The scheduled GitHub Actions workflow commits and deploys the refreshed `config.json`: every 10 minutes in March–May (China time), every 30 minutes otherwise. GitHub scheduling can be delayed.
6. If Shenzhen fetching fails, existing Shenzhen data remains. If regional fetching fails, the thunder monitor fails closed, without generating an estimate. Details are written to `logs/run.log`.

## Requirements

- Python 3.10+ (standard library only; no browser or third-party Python packages required)

## Local Development

Run a static server (recommended):

```bash
python -m http.server 8080
```

Open:

```text
http://localhost:8080
```

Run one-time live weather update:

```bash
python auto_update/updater.py
```

## Configuration (`config.json`)

### Data blocks used by front-end

- `LIVE_DATA`: live weather values (`t`, `r_day`, `r_1h`, `p`, `time`, etc.)
- `MANUAL_CONFIG`: official short forecast shown on the homepage card
- `FORECAST`: seven official daily forecast entries for `forecast.html`
- `WARNINGS`: active Shenzhen warnings for `warnings.html`
- `ALERT_CONFIG`: the first active warning for the homepage modal
- `THUNDER_MONITOR_CONFIG`: fixed-speed monitor settings and site-wide default mode
- `THUNDER_ALERT_CONFIG`: official regional warning snapshot, estimates, radar and filtering audit

## 上游雷暴估测（非官方预警）

开关仅在 GitHub 后台，网页不提供访客开关，也不读取浏览器中旧的开关记忆。上传此版本后，管理员在仓库 **Actions → 自动更新天气数据 → Run workflow** 中选择 `main` 分支和监测模式，再点击运行：

- **保持当前设置**：仅更新数据，不改变全站模式（定时任务也采用此行为）。
- **自动（3–5 月）**：仅在北京时间 3–5 月启用。
- **开启**：全年启用，仍须有有效官方上游预警才能生成估测提示。
- **关闭**：关闭全站上游雷暴估测，不影响深圳官方预警弹窗。

模式保存到 `config.json` 的 `THUNDER_MONITOR_CONFIG.default_mode`（`auto` / `on` / `off`），后续定时更新保持这一选择，直到管理员再次修改。运行摘要显示已保存模式；工作流成功发布后对所有访客生效，已打开的网页每 5 分钟读取新配置，也可刷新立即读取。此开关不是即时推送，需等待工作流与 Pages 发布完成。

数据源是广东气象部门页面使用的共享接口 [ActiveYJ.json](https://www.gd121.cn/api/ftproot/ActiveYJ.json)，不是八个独立城市 API。按地区代码筛选阳江（4417）、肇庆（4412）、江门（4407）、中山（4420）、珠海（4404）、佛山（4406）、广州（4401）、东莞（4419），县区归入所属城市。只取雷雨大风、暴雨、雷电、雷暴、冰雹；暴雨信号并不保证存在雷暴。

计算规则：

- 每个县区/预警类型只保留最新记录，排除解除、未来、无效时间及发布超过 6 小时的记录。6 小时覆盖最远城市耗时＋30 分钟保留期，避免提前撤销；抵达＋30 分钟到期判断仍优先执行。
- 先选投影距离最近的城市，再选该城市最新的有效相关预警。珠海先发、阳江后发时，仍按珠海的发布时间计算；远处新信号不会重置主提示。
- 每个城市使用固定的近似中心坐标，县区预警不使用县区边界。中心经线投影到深圳参考纬度 22.5431°N，参考经度 114.0579°E；不使用斜向直线距离。
- 距离（km）＝6371.0088 × cos（深圳纬度）× 经度差（弧度）；耗时＝距离 ÷ **50 km/h**，四舍五入到分钟。抵达时刻＝原始官方预警发布时间＋耗时。
- 倒计时每秒按现实时间计算，不因刷新重新起算。归零后进入 **30 分钟保留期**，到抵达时刻＋30 分钟撤销；数据过期/不可用或手动关闭也会撤销。后台标签页计时可能被浏览器降频，返回页面时立即复核。
- 距离可信度：≤60 km 较高，60–150 km 中等，>150 km 较低；未经统计校准，不是命中概率。
- 有多个城市信号不意味着同一飑线。估测假设南北向飑线以 50 km/h 向东推进并覆盖深圳纬度，系统不提取实际雷暴速度/方向，也不追踪回波；不代替官方预警。

| 城市 | 投影距离 km | 耗时（分钟） |
|---|---:|---:|
| 阳江 | 213.2 | 256 |
| 肇庆 | 163.6 | 196 |
| 江门 | 100.2 | 120 |
| 中山 | 68.3 | 82 |
| 珠海 | 49.4 | 59 |
| 佛山 | 96.2 | 115 |
| 广州 | 81.5 | 98 |
| 东莞 | 31.4 | 38 |

雷暴弹窗优先，关闭或失效后显示深圳官方预警（如有）。弹窗含逐条计算和官方原文链接；图片来自 [中央气象台华南雷达页](https://www.nmc.cn/publish/radar/huanan.html)，解析图片 UTC 时次并转为北京时间。仅显示 45 分钟内成功获取的图片，失败或过旧时显示官方页面链接，不冒充最新图。

上游数据有效期最多 45 分钟，且不超过主信号的抵达＋30 分钟。页面每 5 分钟重新读取静态快照；GitHub 定时任务不是实时推送，不保证 10 分钟内可见。没有有效上游信号不等于深圳没有雷暴风险。

测试（模拟数据不会写入正式配置）：

```bash
python3 -B -m unittest discover -s tests -v
node tests/test_alerts.cjs
```

可选实际浏览器测试（需安装 Playwright 及 Chromium；已有 Chrome 时可用下面的命令）：

```bash
TEST_BROWSER_CHANNEL=chrome node tests/test_browser.cjs
TEST_BROWSER_CHANNEL=chrome node tests/test_ui.cjs
```

浏览器测试使用隔离会话与拦截响应，不改写正式数据；截图输出到 `/private/tmp/thunder-desktop.png`、`/private/tmp/thunder-mobile.png`（macOS）。

`test_ui.cjs` 另外验证导航下拉菜单跨间隙保持展开、点击空白处/按 Esc 关闭，以及最长看板娘台词在 PC、手机和短屏幕下的自适应与滚动。对话框不会将字号缩到 12px 以下；长台词显示时间按长度延长，最长 30 秒。

### Logging

- `LOG_CONFIG.error_log`: error log output path
- Current default path: `logs/run.log`

## Error Logging

When fetch or update fails, scripts append a block to `logs/run.log` with:

- timestamp
- action name
- error message
- optional output snapshot (page source / response snippet)
- traceback (if available)

## GitHub Actions

Workflow file: `.github/workflows/update.yml`

Before publishing, set **Settings → Pages → Build and deployment → Source → GitHub Actions**, and allow **Actions → General → Workflow permissions → Read and write permissions**. Run the “自动更新天气数据” workflow manually once after uploading. The workflow explicitly deploys Pages because `GITHUB_TOKEN` commits do not trigger branch-source Pages builds ([GitHub documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)). No personal access token is needed for this scheduled deployment.

Current workflow uses the seasonal cadence above and executes `auto_update/updater.py`. It accesses the following public official source files:

- `https://weather.121.com.cn/data_cache/szWeather/sz10day_new.js`
- `https://weather.121.com.cn/data_cache/szWeather/szOssmo.js`
- `https://weather.121.com.cn/data_cache/szWeather/alarm/szAlarm.js`

The workflow runs deterministic Python/JavaScript tests before updating, commits only `config.json`, then explicitly deploys the static site; runtime logs are kept out of weather-data commits.

## Common Issues

1. `Official data file did not contain a JSON object`
	 - The source format may have changed. Update the parser in `auto_update/utils/util_updater.py`.

2. The workflow reports no new commit
	 - This means the official data did not change since the last successful run.

## License

This repository currently has no explicit license file.
