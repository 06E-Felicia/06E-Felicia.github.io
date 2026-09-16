import json
import traceback
from datetime import datetime
from pathlib import Path

__all__ = ["ConfigurationService", "LoggingService"]

# config management and error logging utilities
CONFIG_FILE = Path("config.json")
DEFAULT_ERROR_LOG = Path("logs/run.log")


class LoggingService:
    def __init__(self, error_log_path=DEFAULT_ERROR_LOG):
        self.error_log_path = error_log_path
        self.error_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.error_log_path.open("w", encoding="utf-8") as f:
            f.write(f"--- Logging started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    def _log_error(self, action, error, output=None):
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

        with self.error_log_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    
    def log_error(self, action, error, output=None):
        try:
            self._log_error(action, error, output)
        except Exception as e:
            print(f"❌ 记录错误失败: {e}")


class ConfigurationService:
    def __init__(self, config_path=CONFIG_FILE, logger: LoggingService = None):
        self.config_path = config_path
        self.logger = logger
        if self.logger is None:
            self.logger = LoggingService()
        self.config = self.read_config()

    def _load_config(self):
        with self.config_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_config(self, config):
        # refresh config file with new content
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
            f.write("\n")
    
    def read_config(self):
        try:
            return self._load_config()
        except Exception as e:
            print(f"❌ 读取配置失败: {e}")
            self.logger.log_error("autoupdate.load_config", str(e))
            raise SystemExit(1)

    def save_config(self):
        try:
            self._save_config(self.config)
        except Exception as e:
            print(f"❌ 写入配置失败: {e}")
            self.logger.log_error("autoupdate.save_config", str(e))
            raise SystemExit(1)

    def get_value(self, key, default=None):
        return self.config.get(key, default)

    def set_value(self, key, value):
        self.config[key] = value
        self.save_config()
    
    def get_values(self, keys, default_values=None):
        if default_values is None:
            default_values = [None] * len(keys)
        elif len(default_values) != len(keys):
            raise ValueError("keys 和 default_values 长度必须一致")

        return [self.config.get(key, default) for key, default in zip(keys, default_values)]

    def set_values(self, key_value_pairs):
        self.config.update(key_value_pairs)
        self.save_config()
