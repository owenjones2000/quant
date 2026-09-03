"""自定义策略：多周期均线+KDJ压力支撑交易系统
基于 docs/STRATEGY-CONTEXT.md 决策文档实现
"""
import numpy as np
from MyTT import *


# ============ 补充函数 ============

def VALUEWHEN(S_BOOL, X):
    """条件成立时取X的值，否则保持上一次的值"""
    out = np.full_like(X, np.nan, dtype=float)
    last = np.nan
    for i in range(len(S_BOOL)):
        if S_BOOL[i]:
            last = X[i]
        out[i] = last
    return out


# ============ 指标计算 ============

def calc_indicators(C, H, L, O, V):
    """计算所有指标，返回字典"""
    # 均线
    ma5 = MA(C, 5)
    ma10 = MA(C, 10)
    ma15 = MA(C, 15)
    ma30 = MA(C, 30)
    ma50 = MA(C, 50)
    ma120 = MA(C, 120)
    ma240 = MA(C, 240)

    # KDJ双周期
    rsv = (C - LLV(L, 5)) / (HHV(H, 5) - LLV(L, 5) + 1e-10) * 100
    k = SMA(rsv, 3, 1)
    d = SMA(k, 3, 1)
    j = 3 * k - 2 * d

    rsv24 = (C - LLV(L, 55)) / (HHV(H, 55) - LLV(L, 55) + 1e-10) * 100
    k24 = SMA(rsv24, 3, 1)
    d24 = SMA(k24, 3, 1)
    j24 = 3 * k24 - 2 * d24

    # 压力线/支撑线
    pressure = VALUEWHEN(CROSS(j24, j), H)   # J24上穿J时的高点
    support = VALUEWHEN(CROSS(j, j24), L)     # J上穿J24时的低点

    return {
        "ma5": ma5, "ma10": ma10, "ma15": ma15, "ma30": ma30,
        "ma50": ma50, "ma120": ma120, "ma240": ma240,
        "j": j, "j24": j24,
        "pressure": pressure, "support": support,
    }


# ============ 信号函数 ============

NEAR_PCT = 0.03  # ±3% 算"附近"


def _near(price, target):
    """价格是否在目标附近(±3%)"""
    return np.abs(price - target) / (target + 1e-10) <= NEAR_PCT


def _stand_above_ma15(C, ind, i):
    """站上确认：收盘>MA15 且 MA5已上穿MA10"""
    if i < 1:
        return False
    above_ma15 = C[i] > ind["ma15"][i]
    ma5_cross_ma10 = ind["ma5"][i] > ind["ma10"][i] and ind["ma5"][i-1] <= ind["ma10"][i-1]
    ma5_above_ma10 = ind["ma5"][i] > ind["ma10"][i]
    return above_ma15 and (ma5_cross_ma10 or ma5_above_ma10)


def _broke_pressure_recently(C, pressure, i, lookback=10):
    """最近N天内是否突破过压力线"""
    for k in range(max(0, i - lookback), i):
        if not np.isnan(pressure[k]) and C[k] > pressure[k]:
            return True
    return False


def buy_signal(C, H, L, O, V):
    """买入信号 (返回bool数组)"""
    ind = calc_indicators(C, H, L, O, V)
    n = len(C)
    sig = np.zeros(n, dtype=bool)

    for i in range(60, n):  # 需要足够历史数据
        if not _stand_above_ma15(C, ind, i):
            continue

        p = ind["pressure"][i]
        is_bull = C[i] > ind["ma50"][i]

        # P1: 突破压力线后回调到MA10/MA15附近
        if not np.isnan(p) and _broke_pressure_recently(C, ind["pressure"], i):
            if _near(C[i], ind["ma10"][i]) or _near(C[i], ind["ma15"][i]):
                sig[i] = True
                continue

        # P2: 回调到MA10/MA15附近 (震荡市常规买入)
        if _near(C[i], ind["ma10"][i]) or _near(C[i], ind["ma15"][i]):
            if not np.isnan(ind["support"][i]) and C[i] > ind["support"][i]:
                sig[i] = True
                continue

        # P3: 长期均线支撑反弹
        for ma_val in [ind["ma50"][i], ind["ma120"][i], ind["ma240"][i]]:
            if not np.isnan(ma_val) and _near(C[i], ma_val):
                sig[i] = True
                break

    return sig


def sell_signal(C, H, L, O, V):
    """卖出信号 (返回bool数组)"""
    ind = calc_indicators(C, H, L, O, V)
    n = len(C)
    sig = np.zeros(n, dtype=bool)

    for i in range(60, n):
        p = ind["pressure"][i]

        # 到达压力线附近止盈 (±2%)
        if not np.isnan(p) and abs(C[i] - p) / (p + 1e-10) <= 0.02:
            # 但如果已突破压力线则不卖
            if C[i] < p * 1.02:
                sig[i] = True
                continue

        # 跌破MA50清仓
        if C[i] < ind["ma50"][i] and (i < 1 or C[i-1] >= ind["ma50"][i-1]):
            sig[i] = True
            continue

        # 跌破MA15减仓警告 (连续2天)
        if i >= 2 and C[i] < ind["ma15"][i] and C[i-1] < ind["ma15"][i-1]:
            sig[i] = True

    return sig


# ============ 用于回测的简化版 (满仓进出) ============

def buy_signal_simple(C, H, L, O, V):
    """简化买入：站上MA15确认 + 回调到均线附近"""
    return buy_signal(C, H, L, O, V)


def sell_signal_simple(C, H, L, O, V):
    """简化卖出：压力线止盈 / 跌破MA50"""
    return sell_signal(C, H, L, O, V)
