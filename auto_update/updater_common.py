import json
import traceback
from datetime import datetime
from pathlib import Path

CONFIG_FILE = Path("config.json")
DEFAULT_ERROR_LOG = "logs/err.log"


def load_config():
    with CONFIG_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
        f.write("\n")


def _get_error_log_path(config):
    log_cfg = (config or {}).get("LOG_CONFIG", {})
    return Path(log_cfg.get("error_log", DEFAULT_ERROR_LOG))


def log_error(config, action, error, output=None):
    log_path = _get_error_log_path(config)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}",
        f"ERROR: {error}",
    ]
    if output:
        lines.append(f"OUTPUT: {output}")

    trace = traceback.format_exc().strip()
    if trace and trace != "NoneType: None":
        lines.append("TRACEBACK:")
        lines.append(trace)

    lines.append("\n" * 2)

    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
