"""K线数据读写 - PostgreSQL"""
import pandas as pd
from psycopg2.extras import execute_values
from data.db import get_conn


# ============ 写入 ============

def upsert_daily(code: str, df: pd.DataFrame):
    """写入日K线 (upsert)，自动计算涨跌幅和涨停标记"""
    if df.empty:
        return
    limit = 0.195 if code.startswith("30") or code.startswith("68") else 0.095

    # 取DB中最后一条收盘价作为第一条的前收
    prev_close_db = None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                first_date = df.index[0] if isinstance(df.index[0], str) else df.index[0].strftime("%Y-%m-%d")
                cur.execute("SELECT close FROM kline_daily WHERE code=%s AND date < %s ORDER BY date DESC LIMIT 1",
                            (code, first_date))
                row = cur.fetchone()
                if row:
                    prev_close_db = float(row[0])
    except Exception:
        pass

    rows = []
    closes = df["close"].values.astype(float)
    for i, (idx, r) in enumerate(df.iterrows()):
        date = idx if isinstance(idx, str) else idx.strftime("%Y-%m-%d")
        if i == 0:
            prev = prev_close_db
        else:
            prev = float(closes[i - 1])
        change_pct = round((float(r["close"]) - prev) / prev * 100, 2) if prev else None
        is_limit_up = change_pct is not None and change_pct >= limit * 100
        rows.append((code, date, float(r["open"]), float(r["high"]),
                      float(r["low"]), float(r["close"]),
                      int(r["volume"]), float(r.get("amount", 0)),
                      change_pct, is_limit_up))
    sql = """INSERT INTO kline_daily (code, date, open, high, low, close, volume, amount, change_pct, is_limit_up)
             VALUES %s
             ON CONFLICT (code, date) DO UPDATE SET
               open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
               close=EXCLUDED.close, volume=EXCLUDED.volume, amount=EXCLUDED.amount,
               change_pct=EXCLUDED.change_pct, is_limit_up=EXCLUDED.is_limit_up"""
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

def _fetchall_to_df(cur, columns: list) -> pd.DataFrame:
    """cursor结果转DataFrame，避免pd.read_sql的警告"""
    rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def read_daily(code: str, count: int = 250) -> pd.DataFrame:
    """读取日K线，返回最近count条"""
    sql = """SELECT date, open, high, low, close, volume, amount, change_pct, is_limit_up
             FROM kline_daily WHERE code=%s ORDER BY date DESC LIMIT %s"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (code, count))
            df = _fetchall_to_df(cur, ["date","open","high","low","close","volume","amount","change_pct","is_limit_up"])
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
             FROM kline_30m WHERE code=%s ORDER BY datetime DESC LIMIT %s"""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (code, count))
            df = _fetchall_to_df(cur, ["datetime","open","high","low","close","volume"])
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
