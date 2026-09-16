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
5. The scheduled GitHub Actions workflow commits the refreshed `config.json` every 30 minutes.
6. If fetching fails, the existing configuration remains in place and details are written to `logs/run.log`.

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

Current workflow runs on a 30-minute cron and executes `auto_update/updater.py`. It accesses the following public official source files:

- `https://weather.121.com.cn/data_cache/szWeather/sz10day_new.js`
- `https://weather.121.com.cn/data_cache/szWeather/szOssmo.js`
- `https://weather.121.com.cn/data_cache/szWeather/alarm/szAlarm.js`

The workflow commits only `config.json`; runtime logs are kept out of weather-data commits.

## Common Issues

1. `Official data file did not contain a JSON object`
	 - The source format may have changed. Update the parser in `auto_update/utils/util_updater.py`.

2. The workflow reports no new commit
	 - This means the official data did not change since the last successful run.

## License

This repository currently has no explicit license file.
