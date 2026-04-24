"""A股数据提供层 - 优先读本地PostgreSQL，无数据时回退AKShare"""
import akshare as ak
import pandas as pd
from data.store import read_daily, read_30m, upsert_daily, upsert_30m


def get_stock_list() -> pd.DataFrame:
    """获取全部A股列表"""
    # 先尝试DB
    try:
        from data.db import get_conn
        with get_conn() as conn:
            df = pd.read_sql("SELECT code AS 代码, name AS 名称 FROM stock_info WHERE status=1", conn)
            if len(df) > 100:
                return df
    except Exception:
        pass
    # 回退AKShare
    df = ak.stock_zh_a_spot()
    df = df.rename(columns={"代码": "代码", "名称": "名称"})
    return df[["代码", "名称"]].reset_index(drop=True)


def _to_sina_code(symbol: str) -> str:
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}{symbol}"


def get_daily_kline(symbol: str, count: int = 250) -> pd.DataFrame:
    """获取日K线 - 优先本地DB"""
    df = read_daily(symbol, count)
    if len(df) >= min(count, 30):
        return df
    # DB数据不足，从AKShare拉取并存入DB
    try:
        code = _to_sina_code(symbol)
        remote = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
        if remote.empty:
            return df
        remote["date"] = remote["date"].astype(str)
        remote = remote.set_index("date")
        remote = remote[["open", "high", "low", "close", "volume"]].tail(max(count, 500))
        remote["amount"] = 0
        upsert_daily(symbol, remote)
        return remote.tail(count)
    except Exception:
        return df  # 网络失败就用DB里有的


def get_minute_kline(symbol: str, period: str = "30", count: int = 100) -> pd.DataFrame:
    """获取分钟K线 - 优先本地DB (仅30分钟线)"""
    if period == "30":
        df = read_30m(symbol, count)
        if len(df) >= min(count, 20):
            return df
    # 回退AKShare
    try:
        code = _to_sina_code(symbol)
        remote = ak.stock_zh_a_minute(symbol=code, period=period, adjust="qfq")
        if remote.empty:
            return pd.DataFrame()
        remote["day"] = remote["day"].astype(str)
        remote = remote.set_index("day")
        remote = remote[["open", "high", "low", "close", "volume"]].tail(count)
        if period == "30":
            remote.index.name = "datetime"
            upsert_30m(symbol, remote)
        return remote
    except Exception:
        return pd.DataFrame()
