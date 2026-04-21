"""配置文件"""
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "scan_interval_minutes": 3,
    "notify": {
        "feishu_webhook": "",
        "email": {
            "smtp_host": "smtp.qq.com",
            "smtp_port": 465,
            "user": "",
            "password": "",
            "to": "",
        },
    },
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
