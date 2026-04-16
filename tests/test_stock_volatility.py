from stock_volatility import (
    compute_daily_volatility_stats,
    compute_normal_90_interval_stats,
    percentile,
    to_tencent_symbol,
)


def test_percentile_linear_interpolation():
    values = [0.01, 0.02, 0.03, 0.04, 0.05]
    assert round(percentile(values, 0.7), 6) == 0.038
    assert round(percentile(values, 0.9), 6) == 0.046


def test_compute_daily_volatility_stats_from_closes():
    closes = [100, 102, 99.96, 104.958, 101.80926]
    stats = compute_daily_volatility_stats(symbol="MOCK", closes=closes)

    assert stats.symbol == "MOCK"
    assert stats.trading_days == 4
    assert round(stats.avg_daily_volatility, 6) == 0.03
    assert round(stats.p70_daily_volatility, 6) == 0.032
    assert round(stats.p90_daily_volatility, 6) == 0.044


def test_compute_normal_90_interval_stats_from_closes():
    closes = [100, 102, 99.96, 104.958, 101.80926]
    normal_stats = compute_normal_90_interval_stats(symbol="MOCK", closes=closes)

    assert normal_stats.symbol == "MOCK"
    assert normal_stats.trading_days == 4
    assert round(normal_stats.mean_daily_return, 6) == 0.005
    assert round(normal_stats.std_daily_return, 6) == 0.036968
    assert round(normal_stats.lower_90_interval, 6) == -0.055808
    assert round(normal_stats.upper_90_interval, 6) == 0.065808


def test_to_tencent_symbol_for_a_share_inputs():
    assert to_tencent_symbol("600795.SS") == "sh600795"
    assert to_tencent_symbol("000001.SZ") == "sz000001"
    assert to_tencent_symbol("600795") == "sh600795"
    assert to_tencent_symbol("000001") == "sz000001"
