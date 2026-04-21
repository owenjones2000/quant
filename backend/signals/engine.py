"""信号引擎 - 对自选股运行指标公式，产生买卖信号"""
from datetime import datetime
from data.cache import batch_fetch_klines
from tdx_parser.screener import load_watchlist
from MyTT import *


# ============ 预置信号公式 ============

def signal_macd_buy(C, H, L, O, V):
    """MACD金叉买入信号"""
    dif, dea, macd = MACD(C)
    return RET(CROSS(dif, dea))

def signal_macd_sell(C, H, L, O, V):
    """MACD死叉卖出信号"""
    dif, dea, macd = MACD(C)
    return RET(CROSS(dea, dif))

def signal_boll_lower(C, H, L, O, V):
    """触及布林下轨"""
    upper, mid, lower = BOLL(C)
    return RET(C) <= RET(lower)

SIGNALS = {
    "macd_buy":    {"name": "MACD金叉",    "type": "buy",  "fn": signal_macd_buy},
    "macd_sell":   {"name": "MACD死叉",    "type": "sell", "fn": signal_macd_sell},
    "boll_lower":  {"name": "触及布林下轨", "type": "buy",  "fn": signal_boll_lower},
}


def scan_all_signals(watchlist: list = None) -> list:
    """扫描自选股所有信号 - 批量拉取行情，每只股票只请求一次"""
    if watchlist is None:
        watchlist = [s["code"] for s in load_watchlist()]

    # 一次性并发拉取所有行情
    klines = batch_fetch_klines(watchlist, max_workers=10)

    results = []
    for code, df in klines.items():
        C = df['close'].values
        H = df['high'].values
        L = df['low'].values
        O = df['open'].values
        V = df['volume'].values

        for key, sig in SIGNALS.items():
            try:
                if sig["fn"](C, H, L, O, V):
                    results.append({
                        "code": code,
                        "close": float(C[-1]),
                        "signal": sig["name"],
                        "type": sig["type"],
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    })
            except Exception:
                continue
    return results
