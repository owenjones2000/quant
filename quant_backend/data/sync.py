"""数据同步任务 - 从AKShare拉取数据写入PostgreSQL"""
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import akshare as ak
from data.store import upsert_daily, upsert_30m, upsert_stock_info, get_latest_date, get_stock_count
from tdx_parser.daily_scanner import get_filtered_pool


def _to_sina_code(symbol: str) -> str:
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}{symbol}"


def _board(code: str) -> str:
    if code.startswith("60"): return "main"
    if code.startswith("00"): return "sme"
    if code.startswith("30"): return "gem"
    return "other"


# ============ 全量同步 ============

def sync_stock_list():
    """同步股票列表到DB"""
    df = ak.stock_zh_a_spot()
    stocks = []
    for _, row in df.iterrows():
        c = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
        if c.startswith(("60", "00", "30")):
            market = "sh" if c.startswith("6") else "sz"
            stocks.append({"code": c, "name": row["名称"], "market": market, "board": _board(c)})
    upsert_stock_info(stocks)
    print(f"✅ 股票列表同步完成: {len(stocks)}只")
    return len(stocks)


def sync_daily_full(codes: list = None, count: int = 500, max_workers: int = 8):
    """全量同步日K线"""
    if codes is None:
        codes = get_filtered_pool()
    total = len(codes)
    done = 0
    failed = 0
    start = time.time()

    def _fetch_and_save(code):
        try:
            sina_code = _to_sina_code(code)
            df = ak.stock_zh_a_daily(symbol=sina_code, adjust="qfq")
            if df.empty:
                return False
            df["date"] = df["date"].astype(str)
            df = df.set_index("date")
            df = df[["open", "high", "low", "close", "volume"]].tail(count)
            df["amount"] = 0
            upsert_daily(code, df)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_and_save, c): c for c in codes}
        for f in as_completed(futures):
            if f.result():
                done += 1
            else:
                failed += 1
            if (done + failed) % 100 == 0:
                print(f"  进度: {done+failed}/{total} 成功:{done} 失败:{failed}")

    elapsed = time.time() - start
    print(f"✅ 日K线全量同步完成: {done}成功 {failed}失败 耗时{elapsed:.0f}秒")
    return done


def sync_daily_incremental(codes: list = None, max_workers: int = 8):
    """增量同步日K线 - 只拉最新数据"""
    if codes is None:
        codes = get_filtered_pool()
    done = 0
    start = time.time()

    def _fetch_incr(code):
        try:
            latest = get_latest_date(code)
            if not latest:
                return _fetch_full_one(code)
            sina_code = _to_sina_code(code)
            df = ak.stock_zh_a_daily(symbol=sina_code, adjust="qfq")
            if df.empty:
                return False
            df["date"] = df["date"].astype(str)
            df = df.set_index("date")
            df = df[["open", "high", "low", "close", "volume"]]
            # 只取latest之后的新数据
            new_df = df[df.index > latest]
            if new_df.empty:
                return True
            new_df["amount"] = 0
            upsert_daily(code, new_df)
            return True
        except Exception:
            return False

    def _fetch_full_one(code):
        try:
            sina_code = _to_sina_code(code)
            df = ak.stock_zh_a_daily(symbol=sina_code, adjust="qfq")
            if df.empty:
                return False
            df["date"] = df["date"].astype(str)
            df = df.set_index("date")
            df = df[["open", "high", "low", "close", "volume"]].tail(500)
            df["amount"] = 0
            upsert_daily(code, df)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_incr, c): c for c in codes}
        for f in as_completed(futures):
            if f.result():
                done += 1

    elapsed = time.time() - start
    print(f"✅ 日K线增量同步: {done}/{len(codes)} 耗时{elapsed:.0f}秒")
    return done


def sync_30m(codes: list = None, count: int = 200, max_workers: int = 8):
    """同步30分钟K线"""
    if codes is None:
        codes = get_filtered_pool()
    done = 0

    def _fetch(code):
        try:
            sina_code = _to_sina_code(code)
            df = ak.stock_zh_a_minute(symbol=sina_code, period="30", adjust="qfq")
            if df.empty:
                return False
            df["day"] = df["day"].astype(str)
            df = df.set_index("day")
            df = df[["open", "high", "low", "close", "volume"]].tail(count)
            df.index.name = "datetime"
            upsert_30m(code, df)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch, c): c for c in codes}
        for f in as_completed(futures):
            if f.result():
                done += 1

    print(f"✅ 30分钟K线同步: {done}/{len(codes)}")
    return done


# ============ 统一入口 ============

def daily_sync():
    """每日收盘后同步 (增量日线 + 自选股30分钟线)"""
    from tdx_parser.watchlist import load_watchlist
    print(f"[{datetime.now():%H:%M:%S}] 开始每日数据同步...")

    # 1. 增量同步全A日线
    sync_daily_incremental()

    # 2. 自选股30分钟线
    wl_codes = [s["code"] for s in load_watchlist()]
    if wl_codes:
        sync_30m(codes=wl_codes)

    print(f"[{datetime.now():%H:%M:%S}] 数据同步完成, DB中{get_stock_count()}只股票")
