"""自选股管理 - 支持auto/manual分组和标记"""
import json
from pathlib import Path
from datetime import datetime

WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "watchlist.json"


def load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        return json.loads(WATCHLIST_FILE.read_text())
    return []


def save_watchlist(stocks: list):
    WATCHLIST_FILE.write_text(json.dumps(stocks, ensure_ascii=False, indent=2))


def add_to_watchlist(codes: list, group: str = "manual", **extra) -> list:
    """添加股票到自选股
    Args:
        codes: 股票代码列表
        group: 'auto'(自动选入) 或 'manual'(手动添加)
        extra: 额外字段如 tags, reason 等
    """
    wl = load_watchlist()
    existing = {s["code"] for s in wl}
    now = datetime.now().strftime("%Y-%m-%d")
    for c in codes:
        if c not in existing:
            entry = {"code": c, "group": group, "add_date": now, **extra}
            wl.append(entry)
            existing.add(c)
    save_watchlist(wl)
    return wl


def remove_from_watchlist(codes: list, auto_only: bool = False) -> list:
    """移除股票, auto_only=True时只移除自动选入的"""
    wl = load_watchlist()
    if auto_only:
        wl = [s for s in wl if not (s["code"] in codes and s.get("group") == "auto")]
    else:
        wl = [s for s in wl if s["code"] not in codes]
    save_watchlist(wl)
    return wl


def get_by_group(group: str = None) -> list:
    """按分组获取自选股"""
    wl = load_watchlist()
    if group:
        return [s for s in wl if s.get("group") == group]
    return wl


def update_stock(code: str, **fields) -> list:
    """更新某只股票的字段"""
    wl = load_watchlist()
    for s in wl:
        if s["code"] == code:
            s.update(fields)
            break
    save_watchlist(wl)
    return wl
