"""config 模块单元测试 - Requirements: 7.1, 7.2, 7.3"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
import sys

# 确保 backend 目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_config_module(tmp_path):
    """在临时目录中加载 config 模块的隔离版本。"""
    import importlib
    import types

    config_src = Path(__file__).parent.parent / "config.py"
    source = config_src.read_text(encoding="utf-8")
    # 替换 CONFIG_FILE 路径指向临时目录
    source = source.replace(
        'Path(__file__).parent / "config.json"',
        f'Path(r"{tmp_path}") / "config.json"',
    )
    mod = types.ModuleType("config_test_isolated")
    exec(compile(source, "<config>", "exec"), mod.__dict__)
    return mod


class TestDefaultConfigCreation:
    """7.1 - 默认配置自动创建"""

    def test_load_config_creates_file_when_missing(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        cfg_file = tmp_path / "config.json"
        assert not cfg_file.exists()
        result = cfg_mod.load_config()
        assert cfg_file.exists()

    def test_load_config_returns_default_values(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        result = cfg_mod.load_config()
        assert result["scan_interval_minutes"] == 3
        assert result["close_screen_time"] == "15:05"
        assert result["ema_touch_threshold"] == 0.02
        assert result["kline_count"] == 120
        assert result["max_concurrent_fetches"] == 10
        assert result["log_file"] == "logs/screener.log"

    def test_load_config_reads_existing_file(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        custom = {"scan_interval_minutes": 5, "feishu_webhooks": ["https://example.com"]}
        (tmp_path / "config.json").write_text(json.dumps(custom), encoding="utf-8")
        result = cfg_mod.load_config()
        assert result["scan_interval_minutes"] == 5


class TestSaveConfig:
    """7.2 - 原子写入"""

    def test_save_config_writes_file(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        cfg_mod.save_config({"key": "value"})
        data = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert data["key"] == "value"

    def test_save_config_no_tmp_file_remains(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        cfg_mod.save_config({"key": "value"})
        assert not (tmp_path / "config.json.tmp").exists()

    def test_save_config_utf8_chinese(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        cfg_mod.save_config({"name": "测试"})
        text = (tmp_path / "config.json").read_text(encoding="utf-8")
        assert "测试" in text


class TestReloadConfig:
    """7.3 - 热更新"""

    def test_reload_config_picks_up_changes(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        cfg_mod.save_config({"scan_interval_minutes": 3})
        # 模拟外部修改
        (tmp_path / "config.json").write_text(
            json.dumps({"scan_interval_minutes": 10}), encoding="utf-8"
        )
        result = cfg_mod.reload_config()
        assert result["scan_interval_minutes"] == 10


class TestMultipleWebhooks:
    """7.3 - 多 Webhook URL 支持"""

    def test_feishu_webhooks_is_list(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        result = cfg_mod.load_config()
        assert isinstance(result["feishu_webhooks"], list)

    def test_feishu_webhooks_multiple_urls(self, tmp_path):
        cfg_mod = _make_config_module(tmp_path)
        urls = ["https://hook1.example.com", "https://hook2.example.com"]
        cfg_mod.save_config({"feishu_webhooks": urls})
        result = cfg_mod.reload_config()
        assert result["feishu_webhooks"] == urls
