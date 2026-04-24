"""配置模块 - 支持热更新、原子写入"""
import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "feishu_webhooks": [],
    "scan_interval_minutes": 3,
    "close_screen_time": "15:05",
    "ema_touch_threshold": 0.02,
    "max_concurrent_fetches": 10,
    "kline_count": 120,
    "log_file": "logs/screener.log",
}


def load_config() -> dict:
    """读取配置，不存在则创建默认配置文件后返回默认值。"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    """原子写入：先写 .tmp 再 os.replace()，UTF-8，indent=2。"""
    tmp_file = CONFIG_FILE.with_suffix(".json.tmp")
    tmp_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_file, CONFIG_FILE)


def reload_config() -> dict:
    """热更新：重新从文件读取，不重启进程。"""
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
