"""K线数据读写 - PostgreSQL"""
import pandas as pd
from psycopg2.extras import execute_values
from data.db import get_conn


# ============ 写入 ============

def upsert_daily(code: str, df: pd.DataFrame):
    """写入日K线 (upsert)"""
    if df.empty:
        return
    rows = []
    for idx, r in df.iterrows():
        date = idx if isinstance(idx, str) else idx.strftime("%Y-%m-%d")
        rows.append((code, date, float(r["open"]), float(r["high"]),
                      float(r["low"]), float(r["close"]),
                      int(r["volume"]), float(r.get("amount", 0))))
    sql = """INSERT INTO kline_daily (code, date, open, high, low, close, volume, amount)
             VALUES %s
             ON CONFLICT (code, date) DO UPDATE SET
               open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
               close=EXCLUDED.close, volume=EXCLUDED.volume, amount=EXCLUDED.amount"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)


def upsert_30m(code: str, df: pd.DataFrame):
    """写入30分钟K线 (upsert)"""
    if df.empty:
        return
    rows = []
    for idx, r in df.iterrows():
        dt = idx if isinstance(idx, str) else str(idx)
        rows.append((code, dt, float(r["open"]), float(r["high"]),
                      float(r["low"]), float(r["close"]), int(r["volume"])))
    sql = """INSERT INTO kline_30m (code, datetime, open, high, low, close, volume)
             VALUES %s
             ON CONFLICT (code, datetime) DO UPDATE SET
               open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
               close=EXCLUDED.close, volume=EXCLUDED.volume"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)


def upsert_stock_info(stocks: list):
    """批量写入股票信息 [{"code","name","market","board"}]"""
    if not stocks:
        return
    rows = [(s["code"], s["name"], s["market"], s["board"]) for s in stocks]
    sql = """INSERT INTO stock_info (code, name, market, board)
             VALUES %s
             ON CONFLICT (code) DO UPDATE SET
               name=EXCLUDED.name, market=EXCLUDED.market,
               board=EXCLUDED.board, updated_at=NOW()"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)


# ============ 读取 ============

def read_daily(code: str, count: int = 250) -> pd.DataFrame:
    """读取日K线，返回最近count条"""
    sql = """SELECT date, open, high, low, close, volume, amount
             FROM kline_daily WHERE code=%s
             ORDER BY date DESC LIMIT %s"""
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=(code, count))
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    for col in ["open", "high", "low", "close", "amount"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype(int)
    return df


def read_30m(code: str, count: int = 100) -> pd.DataFrame:
    """读取30分钟K线"""
    sql = """SELECT datetime, open, high, low, close, volume
             FROM kline_30m WHERE code=%s
             ORDER BY datetime DESC LIMIT %s"""
    with get_conn() as conn:
        df = pd.read_sql(sql, conn, params=(code, count))
    if df.empty:
        return df
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype(int)
    return df


def get_latest_date(code: str) -> str:
    """获取某只股票最新日K线日期"""
    sql = "SELECT MAX(date) FROM kline_daily WHERE code=%s"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (code,))
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else ""


def get_stock_count() -> int:
    """DB中有多少只股票有日K线"""
    sql = "SELECT COUNT(DISTINCT code) FROM kline_daily"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()[0]
