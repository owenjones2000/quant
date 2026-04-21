"""行情缓存层 - 避免重复请求，支持并发拉取"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from data.provider import get_daily_kline

_cache = {}       # {symbol: {"df": df, "ts": timestamp}}
_TTL = 150        # 缓存有效期秒数 (2.5分钟，配合3分钟扫描间隔)


def get_kline_cached(symbol: str, count: int = 120):
    """带缓存的K线获取"""
    now = time.time()
    if symbol in _cache and (now - _cache[symbol]["ts"]) < _TTL:
        return _cache[symbol]["df"]
    df = get_daily_kline(symbol, count=count)
    _cache[symbol] = {"df": df, "ts": now}
    return df


def batch_fetch_klines(symbols: list, count: int = 120, max_workers: int = 10) -> dict:
    """并发批量拉取K线，返回 {symbol: df}"""
    results = {}
    now = time.time()

    # 分离：已缓存 vs 需拉取
    to_fetch = []
    for s in symbols:
        if s in _cache and (now - _cache[s]["ts"]) < _TTL:
            results[s] = _cache[s]["df"]
        else:
            to_fetch.append(s)

    if not to_fetch:
        return results

    def _fetch(sym):
        try:
            return sym, get_daily_kline(sym, count=count)
        except Exception:
            return sym, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_fetch, s) for s in to_fetch]
        for f in as_completed(futures):
            sym, df = f.result()
            if df is not None and len(df) >= 30:
                _cache[sym] = {"df": df, "ts": time.time()}
                results[sym] = df

    return results


def clear_cache():
    _cache.clear()
