"""轻量回测引擎 - 直接复用MyTT信号函数"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field


@dataclass
class Trade:
    buy_date: str
    buy_price: float
    sell_date: str = ""
    sell_price: float = 0.0
    shares: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class BacktestResult:
    trades: list
    total_return: float          # 总收益率%
    annual_return: float         # 年化收益率%
    max_drawdown: float          # 最大回撤%
    sharpe_ratio: float          # 夏普比率
    win_rate: float              # 胜率%
    profit_loss_ratio: float     # 盈亏比
    total_trades: int            # 总交易次数
    equity_curve: list           # 权益曲线 [{date, equity}]
    benchmark_return: float = 0  # 基准收益率%


def backtest(df: pd.DataFrame, buy_signal_fn, sell_signal_fn,
             init_capital: float = 100000,
             position_pct: float = 1.0,
             commission: float = 0.00025,
             stamp_tax: float = 0.001,
             min_hold_days: int = 1) -> BacktestResult:
    """
    回测引擎
    Args:
        df: K线DataFrame, 需含 open/high/low/close/volume, index为date
        buy_signal_fn: 买入信号函数 (C,H,L,O,V) -> bool数组
        sell_signal_fn: 卖出信号函数 (C,H,L,O,V) -> bool数组
        init_capital: 初始资金
        position_pct: 每次买入仓位比例 (0~1)
        commission: 佣金费率 (双向)
        stamp_tax: 印花税 (卖出)
        min_hold_days: 最少持仓天数
    """
    C = df["close"].values.astype(float)
    H = df["high"].values.astype(float)
    L = df["low"].values.astype(float)
    O = df["open"].values.astype(float)
    V = df["volume"].values.astype(float)
    dates = df.index.strftime("%Y-%m-%d").tolist()
    n = len(C)

    # 生成信号序列
    buy_sig = np.array(buy_signal_fn(C, H, L, O, V), dtype=bool)
    sell_sig = np.array(sell_signal_fn(C, H, L, O, V), dtype=bool)

    # 模拟交易
    cash = init_capital
    shares = 0
    trades = []
    current_trade = None
    hold_days = 0
    equity_curve = []

    for i in range(n):
        equity = cash + shares * C[i]
        equity_curve.append({"date": dates[i], "equity": round(equity, 2)})

        if shares == 0 and buy_sig[i] and i + 1 < n:
            # 次日开盘买入
            buy_price = O[i + 1] if i + 1 < n else C[i]
            available = cash * position_pct
            cost = buy_price * (1 + commission)
            shares = int(available / cost / 100) * 100  # A股100股整数倍
            if shares > 0:
                total_cost = shares * buy_price * (1 + commission)
                cash -= total_cost
                current_trade = Trade(buy_date=dates[min(i+1, n-1)], buy_price=buy_price, shares=shares)
                hold_days = 0

        elif shares > 0:
            hold_days += 1
            if sell_sig[i] and hold_days >= min_hold_days and i + 1 < n:
                # 次日开盘卖出
                sell_price = O[i + 1] if i + 1 < n else C[i]
                revenue = shares * sell_price * (1 - commission - stamp_tax)
                cash += revenue
                current_trade.sell_date = dates[min(i+1, n-1)]
                current_trade.sell_price = sell_price
                current_trade.pnl = revenue - shares * current_trade.buy_price * (1 + commission)
                current_trade.pnl_pct = round(current_trade.pnl / (shares * current_trade.buy_price) * 100, 2)
                trades.append(current_trade)
                shares = 0
                current_trade = None

    # 未平仓按最后收盘价结算
    if shares > 0 and current_trade:
        current_trade.sell_date = dates[-1]
        current_trade.sell_price = C[-1]
        revenue = shares * C[-1] * (1 - commission - stamp_tax)
        current_trade.pnl = revenue - shares * current_trade.buy_price * (1 + commission)
        current_trade.pnl_pct = round(current_trade.pnl / (shares * current_trade.buy_price) * 100, 2)
        trades.append(current_trade)
        cash += revenue
        shares = 0

    # 计算指标
    final_equity = cash
    total_return = (final_equity - init_capital) / init_capital * 100

    # 年化收益率
    days = max(n, 1)
    annual_return = ((final_equity / init_capital) ** (252 / days) - 1) * 100 if days > 0 else 0

    # 最大回撤
    equities = [e["equity"] for e in equity_curve]
    max_drawdown = _calc_max_drawdown(equities)

    # 夏普比率 (日收益率)
    sharpe_ratio = _calc_sharpe(equities)

    # 胜率 & 盈亏比
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t.pnl for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t.pnl for t in losses])) if losses else 1
    profit_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0

    # 基准收益率 (买入持有)
    benchmark_return = (C[-1] - C[0]) / C[0] * 100 if C[0] > 0 else 0

    return BacktestResult(
        trades=[_trade_to_dict(t) for t in trades],
        total_return=round(total_return, 2),
        annual_return=round(annual_return, 2),
        max_drawdown=round(max_drawdown, 2),
        sharpe_ratio=round(sharpe_ratio, 2),
        win_rate=round(win_rate, 2),
        profit_loss_ratio=profit_loss_ratio,
        total_trades=len(trades),
        equity_curve=equity_curve,
        benchmark_return=round(benchmark_return, 2),
    )


def _calc_max_drawdown(equities: list) -> float:
    peak = equities[0]
    max_dd = 0
    for e in equities:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _calc_sharpe(equities: list, rf: float = 0.03) -> float:
    if len(equities) < 2:
        return 0
    returns = np.diff(equities) / equities[:-1]
    if np.std(returns) == 0:
        return 0
    daily_rf = rf / 252
    return float((np.mean(returns) - daily_rf) / np.std(returns) * np.sqrt(252))


def _trade_to_dict(t: Trade) -> dict:
    return {
        "buy_date": t.buy_date, "buy_price": t.buy_price,
        "sell_date": t.sell_date, "sell_price": t.sell_price,
        "shares": t.shares, "pnl": round(t.pnl, 2), "pnl_pct": t.pnl_pct,
    }
