"""A股数据提供层 - 基于AKShare (新浪源为主)"""
import akshare as ak
import pandas as pd
import time


def get_stock_list() -> pd.DataFrame:
    """获取全部A股列表"""
    for _ in range(3):
        try:
            df = ak.stock_zh_a_spot()
            df = df.rename(columns={"code": "代码", "name": "名称"})
            return df[["代码", "名称"]].reset_index(drop=True)
        except Exception:
            time.sleep(1)
    # 降级到baostock
    import baostock as bs
    bs.login()
    rs = bs.query_stock_basic()
    data = []
    while rs.error_code == "0" and rs.next():
        data.append(rs.get_row_data())
    bs.logout()
    df = pd.DataFrame(data, columns=rs.fields)
    df = df[(df["type"] == "1") & (df["status"] == "1")]
    df["代码"] = df["code"].apply(lambda x: x.split(".")[1])
    df = df.rename(columns={"code_name": "名称"})
    return df[["代码", "名称"]].reset_index(drop=True)


def _to_sina_code(symbol: str) -> str:
    """'000001' -> 'sz000001'"""
    prefix = "sh" if symbol.startswith("6") else "sz"
    return f"{prefix}{symbol}"


def get_daily_kline(symbol: str, count: int = 250) -> pd.DataFrame:
    """获取个股日K线 (新浪源, 前复权)"""
    code = _to_sina_code(symbol)
    df = ak.stock_zh_a_daily(symbol=code, adjust="qfq")
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df[["open", "high", "low", "close", "volume"]].tail(count)


def get_minute_kline(symbol: str, period: str = "15", count: int = 100) -> pd.DataFrame:
    """获取分钟K线 (新浪源)"""
    code = _to_sina_code(symbol)
    df = ak.stock_zh_a_minute(symbol=code, period=period, adjust="qfq")
    df["day"] = pd.to_datetime(df["day"])
    df = df.set_index("day")
    return df[["open", "high", "low", "close", "volume"]].tail(count)
