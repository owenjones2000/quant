"""量化交易系统 - API入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from data.provider import get_daily_kline, get_stock_list
from tdx_parser.screener import FORMULAS, screen_stocks, load_watchlist, add_to_watchlist, remove_from_watchlist
from signals.engine import SIGNALS, scan_all_signals
from scheduler import start_scheduler, stop_scheduler, scan_job
from config import load_config, save_config


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
