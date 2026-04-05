# 06E-Felicia's Weather Board

Static weather dashboard for Shenzhen Middle School Meteorology Club.

The page itself is static (`index.html` + assets), while weather data is updated by Python scripts under `auto_update/` that write into `config.json`.

## Highlights

- Static front-end, easy to host on GitHub Pages.
- Config-driven runtime data in `config.json`.
- Live updater with fallback source:
	- `auto_update/updater.py`: fetches live weather values and falls back to API data when needed.
	- `auto_update/utils/util_updater.py`: Selenium scraping + HTTP fallback data fetch.
- Unified error logging to `logs/run.log` when fetch/update actions fail.

## Project Structure

```text
.
|- index.html
|- config.json
|- README.md
|- assets/
|  |- scripts/script.js
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
2. `assets/scripts/script.js` reads:
	 - `LIVE_DATA`
	 - `MANUAL_CONFIG`
	 - `ALERT_CONFIG`
3. `auto_update/updater.py` fetches live weather data from SMCA.
4. If live fetch fails or returns empty values, updater falls back to API data.
5. Updater writes `LIVE_DATA` into `config.json`.
6. If fetch/update fails, scripts append details to `logs/run.log`.

## Requirements

- Python 3.10+
- Google Chrome (for Selenium runtime)
- Python packages:
	- `selenium`
	- `webdriver-manager`
	- `requests`

Install dependencies:

```bash
pip install selenium webdriver-manager requests
```

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
- `MANUAL_CONFIG`: manually controlled forecast card values and images
- `ALERT_CONFIG`: modal alert switch/content

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

Current workflow runs on a 30-minute cron and executes `auto_update/updater.py`.

If you want fully config-driven commits with current code, ensure workflow commits `config.json` (and `logs/run.log` only if you want logs versioned), not `index.html`.

## Common Issues

1. `Import "selenium" could not be resolved`
	 - Install dependencies in the active Python environment.

2. `No live data extracted from page`
	 - Source page structure may have changed.
	 - Update selectors in `auto_update/utils/util_updater.py`.

3. `FileNotFoundError` for chromedriver path under `.wdm`
	 - Clear stale webdriver-manager cache: `rm -rf ~/.wdm`
	 - Reinstall/update dependencies: `pip install -U selenium webdriver-manager`

## License

This repository currently has no explicit license file.
