"""量化交易系统 - API入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from data.provider import get_daily_kline, get_stock_list
from tdx_parser.screener import FORMULAS, screen_stocks
from tdx_parser.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist
from tdx_parser.daily_scanner import daily_pipeline, scan_breakout
from signals.engine import SIGNALS, scan_all_signals
from scheduler import start_scheduler, stop_scheduler, scan_job
from config import load_config, save_config
from backtest.engine import backtest
from MyTT import *
from strategies.ma_kdj_strategy import buy_signal_simple, sell_signal_simple


@asynccontextmanager
async def lifespan(app):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="A股量化交易系统", lifespan=lifespan)


# ---- 行情 ----
@app.get("/api/kline/{symbol}")
def kline(symbol: str, count: int = 120):
    try:
        df = get_daily_kline(symbol, count=count).reset_index()
        df.columns = ["date" if i == 0 else c for i, c in enumerate(df.columns)]
        df["date"] = df["date"].astype(str)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(400, str(e))


# ---- 自选股 ----
@app.get("/api/watchlist")
def get_watchlist():
    return load_watchlist()

@app.post("/api/watchlist/add")
def watchlist_add(codes: list[str]):
    return add_to_watchlist(codes)

@app.post("/api/watchlist/remove")
def watchlist_remove(codes: list[str]):
    return remove_from_watchlist(codes)


# ---- 选股 ----
@app.get("/api/formulas")
def list_formulas():
    return {k: v["name"] for k, v in FORMULAS.items()}

@app.post("/api/screen/{formula_key}")
def screen(formula_key: str, stock_pool: list[str] = None):
    try:
        hits = screen_stocks(formula_key, stock_pool)
        return {"formula": formula_key, "count": len(hits), "hits": hits}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---- 信号 ----
@app.get("/api/signals")
def list_signals():
    return {k: {"name": v["name"], "type": v["type"]} for k, v in SIGNALS.items()}

@app.get("/api/signals/scan")
def scan_signals():
    return scan_all_signals()

@app.post("/api/signals/scan-now")
def scan_now():
    """手动触发一次扫描"""
    scan_job()
    return {"status": "done"}


# ---- 配置 ----
@app.get("/api/config")
def get_config():
    return load_config()

@app.post("/api/config")
def update_config(cfg: dict):
    save_config(cfg)
    return {"status": "ok"}


# ---- 回测 ----
# 预置策略: 买入/卖出信号函数对
STRATEGIES = {
    "ma_kdj_pressure": {
        "name": "多周期均线+KDJ压力支撑",
        "buy": buy_signal_simple,
        "sell": sell_signal_simple,
    },
    "macd": {
        "name": "MACD金叉死叉",
        "buy":  lambda C,H,L,O,V: CROSS(EMA(C,12)-EMA(C,26), EMA(EMA(C,12)-EMA(C,26),9)),
        "sell": lambda C,H,L,O,V: CROSS(EMA(EMA(C,12)-EMA(C,26),9), EMA(C,12)-EMA(C,26)),
    },
    "ma_cross": {
        "name": "MA5/MA20金叉死叉",
        "buy":  lambda C,H,L,O,V: CROSS(MA(C,5), MA(C,20)),
        "sell": lambda C,H,L,O,V: CROSS(MA(C,20), MA(C,5)),
    },
    "kdj": {
        "name": "KDJ超卖买入超买卖出",
        "buy":  lambda C,H,L,O,V: (lambda k,d,j: (j < 20) & CROSS(j,k))(*KDJ(C,H,L)),
        "sell": lambda C,H,L,O,V: (lambda k,d,j: (j > 80) & CROSS(k,j))(*KDJ(C,H,L)),
    },
    "boll": {
        "name": "布林带下轨买上轨卖",
        "buy":  lambda C,H,L,O,V: (lambda u,m,l: C <= l)(*BOLL(C)),
        "sell": lambda C,H,L,O,V: (lambda u,m,l: C >= u)(*BOLL(C)),
    },
}

from pydantic import BaseModel
from typing import Optional

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str
    count: int = 500
    init_capital: float = 100000
    position_pct: float = 1.0
    commission: float = 0.00025
    stamp_tax: float = 0.001

@app.get("/api/backtest/strategies")
def list_strategies():
    return {k: v["name"] for k, v in STRATEGIES.items()}

@app.post("/api/backtest/run")
def run_backtest(req: BacktestRequest):
    if req.strategy not in STRATEGIES:
        raise HTTPException(400, f"未知策略: {req.strategy}, 可用: {list(STRATEGIES.keys())}")
    try:
        df = get_daily_kline(req.symbol, count=req.count)
        strat = STRATEGIES[req.strategy]
        result = backtest(df, strat["buy"], strat["sell"],
                         init_capital=req.init_capital,
                         position_pct=req.position_pct,
                         commission=req.commission,
                         stamp_tax=req.stamp_tax)
        return {
            "symbol": req.symbol,
            "strategy": strat["name"],
            "total_return": result.total_return,
            "annual_return": result.annual_return,
            "max_drawdown": result.max_drawdown,
            "sharpe_ratio": result.sharpe_ratio,
            "win_rate": result.win_rate,
            "profit_loss_ratio": result.profit_loss_ratio,
            "total_trades": result.total_trades,
            "benchmark_return": result.benchmark_return,
            "trades": result.trades,
            "equity_curve": result.equity_curve,
        }
    except Exception as e:
        raise HTTPException(400, str(e))
