# 06E-Felicia's Weather Board

Static weather dashboard for Shenzhen Middle School Meteorology Club.

The page itself is static (`index.html` + assets), while weather data is updated by Python scripts that write into `config.json`.

## Highlights

- Static front-end, easy to host on GitHub Pages.
- Config-driven runtime data in `config.json`.
- Two update scripts:
	- `autoupdate.py`: fetches live weather values.
	- `warning.py`: fetches weather warning icons.
- Unified error logging to `logs/err.log` when fetch/update actions fail.

## Project Structure

```text
.
|- index.html
|- config.json
|- autoupdate.py
|- warning.py
|- updater_common.py
|- assets/
|  |- scripts/script.js
|  |- styles/style.css
|  `- images/
|- logs/
`- .github/workflows/update.yml
```

## How It Works

1. Front-end loads `config.json` on page load.
2. `assets/scripts/script.js` reads:
	 - `LIVE_DATA`
	 - `MANUAL_CONFIG`
	 - `ALERT_CONFIG`
	 - `WARNINGS`
3. Python scripts update `config.json` periodically.
4. If fetch fails, scripts append details to `logs/err.log`.

## Requirements

- Python 3.10+
- Google Chrome (for Selenium runtime)
- Python packages:
	- `selenium`
	- `webdriver-manager`
	- `requests`
	- `beautifulsoup4`

Install dependencies:

```bash
pip install selenium webdriver-manager requests beautifulsoup4
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
python autoupdate.py
```

Run warning updater loop:

```bash
python warning.py
```

## Configuration (`config.json`)

### Data blocks used by front-end

- `LIVE_DATA`: live weather values (`t`, `r_day`, `r_1h`, `p`, `time`, etc.)
- `MANUAL_CONFIG`: manually controlled forecast card values and images
- `ALERT_CONFIG`: modal alert switch/content
- `WARNINGS`: warning icon URLs

### Update behavior

- `AUTOUPDATE_CONFIG`
	- `source_url`
	- `wait_timeout`
	- `time_prefix`
	- class selectors (`wait_class_name`, `item_class_name`, ...)
	- `chrome_args`
	- `targets` (mapping source labels to output keys)
- `WARNING_CONFIG`
	- `source_url`
	- `city_selector_class`
	- `request_timeout`
	- `refresh_interval`
	- `headers`
- `REFRESH_INTERVAL`: fallback interval

### Logging

- `LOG_CONFIG.error_log`: error log output path
- Current default path: `logs/err.log`

## Error Logging

When fetch or update fails, scripts append a block to `logs/err.log` with:

- timestamp
- action name
- error message
- optional output snapshot (page source / response snippet)
- traceback (if available)

## GitHub Actions

Workflow file: `.github/workflows/update.yml`

Current workflow runs on a 10-minute cron and executes `autoupdate.py`.

If you want fully config-driven commits with current code, ensure workflow commits `config.json` (and `logs/err.log` only if you want logs versioned), not `index.html`.

## Common Issues

1. `Import "selenium" could not be resolved`
	 - Install dependencies in the active Python environment.

2. `No live data extracted from page`
	 - Source page structure may have changed.
	 - Update selector-related fields in `AUTOUPDATE_CONFIG`.

3. Warning list stays empty
	 - Verify `WARNING_CONFIG.city_selector_class` and target site availability.

## License

This repository currently has no explicit license file.
