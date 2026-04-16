import argparse
import math
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

import requests


YAHOO_CHART_API = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
EASTMONEY_KLINE_API = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
TENCENT_KLINE_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


@dataclass
class VolatilityStats:
    symbol: str
    trading_days: int
    avg_daily_volatility: float
    p70_daily_volatility: float
    p90_daily_volatility: float


@dataclass
class NormalIntervalStats:
    symbol: str
    trading_days: int
    mean_daily_return: float
    std_daily_return: float
    lower_90_interval: float
    upper_90_interval: float


def percentile(values: List[float], q: float) -> float:
    if not values:
        raise ValueError("values is empty")
    if q < 0 or q > 1:
        raise ValueError("q must be in [0, 1]")

    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]

    pos = (len(sorted_values) - 1) * q
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    if lower == upper:
        return sorted_values[lower]
    weight = pos - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def fetch_daily_closes_from_yahoo(symbol: str, days: int = 365, timeout: int = 15) -> List[float]:
    end_ts = int(time.time())
    start_ts = end_ts - days * 24 * 60 * 60
    url = YAHOO_CHART_API.format(symbol=symbol)
    params = {
        "period1": start_ts,
        "period2": end_ts,
        "interval": "1d",
        "events": "history",
    }

    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()

    error = payload.get("chart", {}).get("error")
    if error:
        raise ValueError(f"Yahoo API error: {error}")

    result = payload.get("chart", {}).get("result")
    if not result:
        raise ValueError("No chart result returned")

    closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
    valid_closes = [float(c) for c in closes if c is not None]
    if len(valid_closes) < 2:
        raise ValueError("Not enough valid close prices")
    return valid_closes


def to_eastmoney_secid(symbol: str) -> Optional[str]:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SS") or normalized.endswith(".SH"):
        code = normalized.split(".")[0]
        return f"1.{code}"
    if normalized.endswith(".SZ"):
        code = normalized.split(".")[0]
        return f"0.{code}"
    if normalized.isdigit() and len(normalized) == 6:
        if normalized.startswith("6"):
            return f"1.{normalized}"
        if normalized.startswith("0") or normalized.startswith("3"):
            return f"0.{normalized}"
    return None


def to_tencent_symbol(symbol: str) -> Optional[str]:
    normalized = symbol.strip().lower()
    if normalized.startswith("sh") or normalized.startswith("sz"):
        return normalized

    upper = symbol.strip().upper()
    if upper.endswith(".SS") or upper.endswith(".SH"):
        code = upper.split(".")[0]
        return f"sh{code}"
    if upper.endswith(".SZ"):
        code = upper.split(".")[0]
        return f"sz{code}"
    if upper.isdigit() and len(upper) == 6:
        if upper.startswith("6"):
            return f"sh{upper}"
        if upper.startswith("0") or upper.startswith("3"):
            return f"sz{upper}"
    return None


def fetch_daily_closes_from_eastmoney(symbol: str, days: int = 365, timeout: int = 15) -> List[float]:
    secid = to_eastmoney_secid(symbol)
    if not secid:
        raise ValueError("Eastmoney source only supports A-share symbols like 600795.SS / 000001.SZ")

    end_day = date.today()
    start_day = end_day - timedelta(days=days)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101",
        "fqt": "1",
        "beg": start_day.strftime("%Y%m%d"),
        "end": end_day.strftime("%Y%m%d"),
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(EASTMONEY_KLINE_API, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    klines = payload.get("data", {}).get("klines", [])
    if not klines:
        raise ValueError("No kline data returned from Eastmoney")

    closes = []
    for row in klines:
        parts = row.split(",")
        if len(parts) < 3:
            continue
        close_txt = parts[2]
        if close_txt in ("", "-"):
            continue
        closes.append(float(close_txt))

    if len(closes) < 2:
        raise ValueError("Not enough valid close prices from Eastmoney")
    return closes


def fetch_daily_closes_from_tencent(symbol: str, days: int = 365, timeout: int = 15) -> List[float]:
    tsymbol = to_tencent_symbol(symbol)
    if not tsymbol:
        raise ValueError("Tencent source only supports A-share symbols like 600795.SS / 000001.SZ")

    params = {"param": f"{tsymbol},day,,,{max(days, 120)},qfq"}
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(TENCENT_KLINE_API, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    stock_data = payload.get("data", {}).get(tsymbol, {})
    rows = stock_data.get("qfqday") or stock_data.get("day") or []
    if not rows:
        raise ValueError("No kline data returned from Tencent")

    closes = []
    for row in rows:
        if len(row) < 3:
            continue
        close_txt = row[2]
        if close_txt in ("", "-"):
            continue
        closes.append(float(close_txt))

    if len(closes) < 2:
        raise ValueError("Not enough valid close prices from Tencent")
    return closes


def fetch_daily_closes(symbol: str, days: int = 365, timeout: int = 15) -> List[float]:
    errors = []
    try:
        return fetch_daily_closes_from_yahoo(symbol=symbol, days=days, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network fallback path
        errors.append(f"Yahoo failed: {exc}")

    try:
        return fetch_daily_closes_from_eastmoney(symbol=symbol, days=days, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network fallback path
        errors.append(f"Eastmoney failed: {exc}")

    try:
        return fetch_daily_closes_from_tencent(symbol=symbol, days=days, timeout=timeout)
    except Exception as exc:  # pragma: no cover - network fallback path
        errors.append(f"Tencent failed: {exc}")

    raise ValueError("; ".join(errors))


def compute_daily_volatility_stats(symbol: str, closes: List[float]) -> VolatilityStats:
    if len(closes) < 2:
        raise ValueError("Need at least 2 close prices")

    daily_abs_returns = []
    for idx in range(1, len(closes)):
        prev_close = closes[idx - 1]
        curr_close = closes[idx]
        if prev_close <= 0:
            continue
        daily_abs_returns.append(abs(curr_close / prev_close - 1.0))

    if not daily_abs_returns:
        raise ValueError("No valid daily returns to compute")

    return VolatilityStats(
        symbol=symbol,
        trading_days=len(daily_abs_returns),
        avg_daily_volatility=sum(daily_abs_returns) / len(daily_abs_returns),
        p70_daily_volatility=percentile(daily_abs_returns, 0.7),
        p90_daily_volatility=percentile(daily_abs_returns, 0.9),
    )


def compute_normal_90_interval_stats(symbol: str, closes: List[float]) -> NormalIntervalStats:
    if len(closes) < 2:
        raise ValueError("Need at least 2 close prices")

    daily_returns = []
    for idx in range(1, len(closes)):
        prev_close = closes[idx - 1]
        curr_close = closes[idx]
        if prev_close <= 0:
            continue
        daily_returns.append(curr_close / prev_close - 1.0)

    if len(daily_returns) < 2:
        raise ValueError("Need at least 2 valid daily returns")

    mean_ret = sum(daily_returns) / len(daily_returns)
    variance = sum((x - mean_ret) ** 2 for x in daily_returns) / (len(daily_returns) - 1)
    std_ret = math.sqrt(variance)
    z_95 = 1.6448536269514722

    return NormalIntervalStats(
        symbol=symbol,
        trading_days=len(daily_returns),
        mean_daily_return=mean_ret,
        std_daily_return=std_ret,
        lower_90_interval=mean_ret - z_95 * std_ret,
        upper_90_interval=mean_ret + z_95 * std_ret,
    )


def print_stats(stats: VolatilityStats, normal_stats: NormalIntervalStats) -> None:
    print(f"股票代码: {stats.symbol}")
    print(f"统计交易日数: {stats.trading_days}")
    print(f"最近一年平均日波动率: {stats.avg_daily_volatility * 100:.2f}%")
    print(f"最近一年 70% 分位交易日波动率: {stats.p70_daily_volatility * 100:.2f}%")
    print(f"最近一年 90% 分位交易日波动率: {stats.p90_daily_volatility * 100:.2f}%")
    print(
        "正态假设下覆盖 90% 交易日区间(去掉两端各5%): "
        f"[{normal_stats.lower_90_interval * 100:.2f}%, {normal_stats.upper_90_interval * 100:.2f}%]"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "统计股票最近一年(默认365天)的日波动率。"
            "日波动率定义为相邻收盘价收益率绝对值 |Close_t / Close_(t-1) - 1|。"
        )
    )
    parser.add_argument(
        "symbol",
        help="股票代码，例如 AAPL、TSLA、600519.SS、000001.SZ",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="向前抓取的自然日数量，默认 365",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    closes = fetch_daily_closes(symbol=args.symbol, days=args.days)
    stats = compute_daily_volatility_stats(symbol=args.symbol, closes=closes)
    normal_stats = compute_normal_90_interval_stats(symbol=args.symbol, closes=closes)
    print_stats(stats, normal_stats)


if __name__ == "__main__":
    main()
