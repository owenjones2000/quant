"""通达信选股公式引擎 - 基于MyTT
用法: 用Python写和通达信几乎一样的选股条件，对全A扫描筛选
"""
import json
import pandas as pd
from pathlib import Path
from data.provider import get_daily_kline, get_stock_list
from MyTT import *

WATCHLIST_FILE = Path(__file__).parent.parent / "data" / "watchlist.json"


def load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        return json.loads(WATCHLIST_FILE.read_text())
    return []


def save_watchlist(stocks: list):
    WATCHLIST_FILE.write_text(json.dumps(stocks, ensure_ascii=False, indent=2))


def add_to_watchlist(codes: list):
    """添加股票到自选股"""
    wl = load_watchlist()
    for c in codes:
        if c not in [s["code"] for s in wl]:
            wl.append({"code": c})
    save_watchlist(wl)
    return wl


def remove_from_watchlist(codes: list):
    wl = load_watchlist()
    wl = [s for s in wl if s["code"] not in codes]
    save_watchlist(wl)
    return wl


# ============ 选股公式 ============
# 每个选股公式是一个函数，接收OHLCV，返回True/False

def formula_ma_cross(C, H, L, O, V):
    """MA5上穿MA20 (金叉)"""
    return RET(CROSS(MA(C, 5), MA(C, 20)))


def formula_volume_break(C, H, L, O, V):
    """放量突破: 成交量>10日最高量 且 收阳"""
    return RET(V) > RET(HHV(V, 10), 2) and RET(C) > RET(O)


def formula_macd_golden(C, H, L, O, V):
    """MACD金叉"""
    dif, dea, macd = MACD(C)
    return RET(CROSS(dif, dea))


def formula_kdj_oversold(C, H, L, O, V):
    """KDJ超卖金叉: J<20后J上穿K"""
    k, d, j = KDJ(C, H, L)
    return RET(j) < 20 and RET(CROSS(j, k))


# 公式注册表 - 可持续扩展
FORMULAS = {
    "ma_cross":       {"name": "MA5上穿MA20",    "fn": formula_ma_cross},
    "volume_break":   {"name": "放量突破",        "fn": formula_volume_break},
    "macd_golden":    {"name": "MACD金叉",       "fn": formula_macd_golden},
    "kdj_oversold":   {"name": "KDJ超卖金叉",    "fn": formula_kdj_oversold},
}


def screen_stocks(formula_key: str, stock_pool: list = None, count: int = 120) -> list:
    """用指定公式扫描股票池
    Args:
        formula_key: 公式key
        stock_pool: 股票代码列表, None则扫描全A
        count: K线条数
    Returns:
        命中的股票代码列表
    """
    if formula_key not in FORMULAS:
        raise ValueError(f"未知公式: {formula_key}, 可用: {list(FORMULAS.keys())}")

    fn = FORMULAS[formula_key]["fn"]
    if stock_pool is None:
        stock_pool = get_stock_list()["代码"].tolist()

    hits = []
    for code in stock_pool:
        try:
            df = get_daily_kline(code, count=count)
            if len(df) < 30:
                continue
            C, H, L, O, V = df['close'].values, df['high'].values, df['low'].values, df['open'].values, df['volume'].values
            if fn(C, H, L, O, V):
                hits.append(code)
        except Exception:
            continue
    return hits
