"""每日自动选股管道
- 扫描：大阳线(≥8%) + 突破压力线(连续2天收盘>压力线3%) + 过滤条件
- 踢出：跌破MA100 且 10天内未重新突破压力位
"""
import numpy as np
import pandas as pd
from datetime import datetime
from data.provider import get_daily_kline, get_stock_list
from data.cache import batch_fetch_klines
from strategies.ma_kdj_strategy import VALUEWHEN
from tdx_parser.watchlist import (
    load_watchlist, add_to_watchlist, remove_from_watchlist, update_stock, get_by_group
)
from MyTT import *


# ============ 股票池过滤 ============

def get_filtered_pool() -> list:
    """获取过滤后的股票池：主板+创业板，排除北交所"""
    stocks = get_stock_list()
    codes = []
    for _, row in stocks.iterrows():
        c = str(row["代码"])
        # 去掉可能的前缀
        pure = c.replace("sh", "").replace("sz", "").replace("bj", "")
        # 主板: 60xxxx(沪), 00xxxx(深)  创业板: 30xxxx
        if pure.startswith(("60", "00", "30")):
            codes.append(pure)
    return codes


# ============ 压力线计算 ============

def _calc_pressure(C, H, L):
    """计算KDJ双周期压力线"""
    rsv = (C - LLV(L, 5)) / (HHV(H, 5) - LLV(L, 5) + 1e-10) * 100
    k = SMA(rsv, 3, 1)
    j = 3 * k - 2 * SMA(k, 3, 1)

    rsv24 = (C - LLV(L, 55)) / (HHV(H, 55) - LLV(L, 55) + 1e-10) * 100
    k24 = SMA(rsv24, 3, 1)
    j24 = 3 * k24 - 2 * SMA(k24, 3, 1)

    return VALUEWHEN(CROSS(j24, j), H)


# ============ 每日扫描选股 ============

def scan_breakout(stock_pool: list = None, max_workers: int = 10) -> list:
    """扫描大阳线突破压力线个股
    条件：
    1. 当日涨幅 ≥ 8%
    2. 连续2天收盘价 > 压力线 * 1.03
    3. 主板+创业板，排除北交所
    Returns:
        [{"code", "name", "change_pct", "close", "pressure", "is_limit_up", "tags"}]
    """
    if stock_pool is None:
        stock_pool = get_filtered_pool()

    klines = batch_fetch_klines(stock_pool, count=120, max_workers=max_workers)
    hits = []

    for code, df in klines.items():
        if len(df) < 60:
            continue
        C = df["close"].values.astype(float)
        H = df["high"].values.astype(float)
        L = df["low"].values.astype(float)
        O = df["open"].values.astype(float)

        # 当日涨幅
        if len(C) < 2:
            continue
        change_pct = (C[-1] - C[-2]) / C[-2] * 100
        if change_pct < 8:
            continue

        # 压力线
        pressure = _calc_pressure(C, H, L)
        p = pressure[-1]
        if np.isnan(p):
            continue

        # 连续2天收盘 > 压力线 * 1.03
        if not (C[-1] > p * 1.03 and C[-2] > p * 1.03):
            continue

        # 涨停判断 (主板10%, 创业板20%)
        limit = 20 if code.startswith("30") else 10
        is_limit_up = change_pct >= limit - 0.5  # 容差0.5%

        tags = ["breakout"]
        if is_limit_up:
            tags.append("limit_up")

        hits.append({
            "code": code,
            "change_pct": round(change_pct, 2),
            "close": float(C[-1]),
            "pressure": round(float(p), 2),
            "is_limit_up": is_limit_up,
            "tags": tags,
        })

    return hits


def auto_add_to_watchlist(hits: list) -> list:
    """将扫描命中的股票加入自选股(auto分组)"""
    for h in hits:
        add_to_watchlist(
            [h["code"]], group="auto",
            tags=h["tags"],
            reason=f"突破压力线{h['pressure']}, 涨幅{h['change_pct']}%",
            pressure_at_add=h["pressure"],
        )
    return load_watchlist()


# ============ 自选股踢出 ============

def check_kickout(max_workers: int = 10) -> list:
    """检查自选股踢出条件：跌破MA100 且 10天内未重新突破压力位
    Returns:
        被踢出的股票代码列表
    """
    auto_stocks = get_by_group("auto")
    if not auto_stocks:
        return []

    codes = [s["code"] for s in auto_stocks]
    klines = batch_fetch_klines(codes, count=120, max_workers=max_workers)
    kickout = []

    for s in auto_stocks:
        code = s["code"]
        if code not in klines:
            continue
        df = klines[code]
        if len(df) < 100:
            continue

        C = df["close"].values.astype(float)
        H = df["high"].values.astype(float)
        L = df["low"].values.astype(float)
        ma100 = MA(C, 100)

        # 条件1: 当前收盘 < MA100
        if C[-1] >= ma100[-1]:
            continue

        # 条件2: 最近10天内未重新突破压力位
        pressure = _calc_pressure(C, H, L)
        p = s.get("pressure_at_add") or pressure[-1]
        if np.isnan(p):
            continue

        recent_10 = C[-10:]
        if any(c > p for c in recent_10):
            continue  # 10天内有突破，保留

        kickout.append(code)

    if kickout:
        remove_from_watchlist(kickout, auto_only=True)

    return kickout


# ============ 每日管道 ============

def daily_pipeline(max_workers: int = 10) -> dict:
    """每日收盘后运行的完整管道"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. 扫描新股
    hits = scan_breakout(max_workers=max_workers)

    # 2. 加入自选股
    if hits:
        auto_add_to_watchlist(hits)

    # 3. 踢出不合格
    kicked = check_kickout(max_workers=max_workers)

    result = {
        "time": now,
        "new_picks": len(hits),
        "picks": hits,
        "kicked_out": kicked,
        "watchlist_count": len(load_watchlist()),
    }
    print(f"[{now}] 选股管道完成: 新增{len(hits)}只, 踢出{len(kicked)}只, 自选股{result['watchlist_count']}只")
    return result
