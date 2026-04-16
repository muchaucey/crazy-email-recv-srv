import argparse
import math
import os
from datetime import date, timedelta
from typing import List, Tuple

import matplotlib.pyplot as plt
import requests


TENCENT_KLINE_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"


def to_tencent_symbol(symbol: str) -> str:
    normalized = symbol.strip().lower()
    if normalized.startswith("sh") or normalized.startswith("sz"):
        return normalized

    upper = symbol.strip().upper()
    if upper.endswith(".SS") or upper.endswith(".SH"):
        return f"sh{upper.split('.')[0]}"
    if upper.endswith(".SZ"):
        return f"sz{upper.split('.')[0]}"
    if upper.isdigit() and len(upper) == 6:
        if upper.startswith("6"):
            return f"sh{upper}"
        return f"sz{upper}"

    raise ValueError("Unsupported symbol. Use formats like 600795.SS or 000001.SZ")


def fetch_daily_ohlc(symbol: str, days: int = 365, timeout: int = 20) -> List[Tuple[float, float, float]]:
    tsymbol = to_tencent_symbol(symbol)
    params = {"param": f"{tsymbol},day,,,{max(days, 120)},qfq"}
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(TENCENT_KLINE_API, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()

    stock_data = payload.get("data", {}).get(tsymbol, {})
    rows = stock_data.get("qfqday") or stock_data.get("day") or []
    if not rows:
        raise ValueError("No kline rows returned from Tencent API")

    # row format: [date, open, close, high, low, volume]
    ohlc: List[Tuple[float, float, float]] = []
    for row in rows:
        if len(row) < 5:
            continue
        close_txt = row[2]
        high_txt = row[3]
        low_txt = row[4]
        if close_txt in ("", "-") or high_txt in ("", "-") or low_txt in ("", "-"):
            continue
        close = float(close_txt)
        high = float(high_txt)
        low = float(low_txt)
        ohlc.append((close, high, low))

    if len(ohlc) < 2:
        raise ValueError("Not enough valid OHLC rows")
    return ohlc


def compute_intraday_volatility(ohlc: List[Tuple[float, float, float]]) -> List[float]:
    # 波动率定义为: (当日最高 - 当日最低) / 昨日收盘
    vol = []
    for i in range(1, len(ohlc)):
        prev_close = ohlc[i - 1][0]
        _, high, low = ohlc[i]
        if prev_close <= 0:
            continue
        vol.append((high - low) / prev_close)

    if len(vol) < 2:
        raise ValueError("Not enough volatility samples")
    return vol


def mean_std(values: List[float]) -> Tuple[float, float]:
    mu = sum(values) / len(values)
    var = sum((x - mu) ** 2 for x in values) / (len(values) - 1)
    return mu, math.sqrt(var)


def normal_pdf(x: float, mu: float, sigma: float) -> float:
    coef = 1.0 / (sigma * math.sqrt(2.0 * math.pi))
    return coef * math.exp(-0.5 * ((x - mu) / sigma) ** 2)


def plot_normal_distribution(symbol: str, vol: List[float], output: str) -> None:
    mu, sigma = mean_std(vol)
    left = max(0.0, mu - 4 * sigma)
    right = mu + 4 * sigma
    n_points = 500
    step = (right - left) / (n_points - 1)
    xs = [left + i * step for i in range(n_points)]
    ys = [normal_pdf(x, mu, sigma) for x in xs]

    plt.figure(figsize=(10, 6))
    plt.hist(vol, bins=30, density=True, alpha=0.45, label="Daily range volatility histogram")
    plt.plot(xs, ys, linewidth=2.2, label="Normal fit")
    plt.axvline(mu, linestyle="--", linewidth=1.5, label=f"mean={mu*100:.2f}%")
    plt.axvline(mu - 1.645 * sigma, linestyle=":", linewidth=1.5, label=f"5%={((mu-1.645*sigma)*100):.2f}%")
    plt.axvline(mu + 1.645 * sigma, linestyle=":", linewidth=1.5, label=f"95%={((mu+1.645*sigma)*100):.2f}%")

    plt.title(f"{symbol} Intraday Volatility Normal Distribution (1Y)")
    plt.xlabel("Volatility = (High - Low) / Previous Close")
    plt.ylabel("Density")
    plt.legend()
    plt.tight_layout()

    out_dir = os.path.dirname(output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    plt.savefig(output, dpi=160)
    plt.close()

    print(f"样本交易日数: {len(vol)}")
    print(f"均值: {mu * 100:.2f}%")
    print(f"标准差: {sigma * 100:.2f}%")
    print(f"覆盖90%交易日区间(正态): [{(mu - 1.645 * sigma) * 100:.2f}%, {(mu + 1.645 * sigma) * 100:.2f}%]")
    print(f"图片已保存: {output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="绘制基于日内振幅(最高-最低)的波动率正态分布图。"
    )
    parser.add_argument("symbol", help="股票代码，例如 600795.SS")
    parser.add_argument("--days", type=int, default=365, help="回溯自然日，默认365")
    parser.add_argument(
        "--output",
        default=f"media/volatility_normal_{date.today().strftime('%Y%m%d')}.png",
        help="输出图片路径",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _ = date.today() - timedelta(days=args.days)
    ohlc = fetch_daily_ohlc(args.symbol, days=args.days)
    vol = compute_intraday_volatility(ohlc)
    plot_normal_distribution(args.symbol, vol, args.output)


if __name__ == "__main__":
    main()
