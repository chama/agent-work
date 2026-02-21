"""Tests for market_data.infra.binance (BinanceFuturesSource)."""

from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.binance import BinanceFuturesSource


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_kline_row(open_time_ms=1700000000000, offset=0):
    """Create a single kline data row for testing."""
    t = open_time_ms + offset * 60000
    return [
        t, "50000.00", "51000.00", "49000.00", "50500.00", "100.500",
        t + 59999, "5050000.00", 1234, "60.300", "3030000.00", "0",
    ]


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_binance_source(self):
        source = create_source("binance", rate_limit_sleep=0)
        assert source.exchange == "binance"

    def test_case_insensitive(self):
        source = create_source("Binance", rate_limit_sleep=0)
        assert source.exchange == "binance"

    def test_unsupported_exchange_raises(self):
        with pytest.raises(ValueError, match="Unsupported exchange"):
            create_source("nonexistent")


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw_data = [_make_kline_row(offset=i) for i in range(3)]

        with patch.object(source._http, "get", return_value=raw_data):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns
        assert df["open"].dtype == float
        assert df["trades"].dtype == int

    def test_empty_response(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_pagination(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        batch1 = [_make_kline_row(offset=i) for i in range(3)]
        batch2 = [_make_kline_row(offset=i + 3) for i in range(2)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            return batch1 if call_count == 1 else batch2

        with patch.object(source._http, "get", side_effect=mock_get):
            # Use limit=3 to trigger pagination
            source._paginate_klines(
                "/fapi/v1/klines",
                {"symbol": "BTCUSDT", "interval": "1m"},
                1700000000000,
                1700000000000 + 600000,
                limit=3,
            )

        assert call_count == 2


# ------------------------------------------------------------------ #
#  Index / Mark Price Klines                                            #
# ------------------------------------------------------------------ #


class TestPriceKlines:
    def test_index_price_columns(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(source._http, "get", return_value=raw):
            df = source.fetch(
                DataType.INDEX_PRICE, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert list(df.columns) == DataType.INDEX_PRICE.columns

    def test_mark_price_columns(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(source._http, "get", return_value=raw):
            df = source.fetch(
                DataType.MARK_PRICE, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert list(df.columns) == DataType.MARK_PRICE.columns


# ------------------------------------------------------------------ #
#  Funding Rate                                                         #
# ------------------------------------------------------------------ #


class TestFundingRate:
    def test_fetch_funding_rate(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw = [
            {
                "symbol": "BTCUSDT",
                "fundingTime": 1700000000000,
                "fundingRate": "0.00010000",
                "markPrice": "50000.00000000",
            },
            {
                "symbol": "BTCUSDT",
                "fundingTime": 1700028800000,
                "fundingRate": "-0.00005000",
                "markPrice": "49800.00000000",
            },
        ]

        with patch.object(source._http, "get", return_value=raw):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 2
        assert list(df.columns) == DataType.FUNDING_RATE.columns
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0001)

    def test_empty(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[]):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Open Interest                                                        #
# ------------------------------------------------------------------ #


class TestOpenInterest:
    def test_fetch_open_interest(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw = [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "12345.678",
                "sumOpenInterestValue": "617283900.00",
                "timestamp": 1700000000000,
            },
        ]

        with patch.object(source._http, "get", return_value=raw):
            df = source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.OPEN_INTEREST.columns
        assert df["open_interest"].iloc[0] == pytest.approx(12345.678)


# ------------------------------------------------------------------ #
#  Long/Short Ratios                                                    #
# ------------------------------------------------------------------ #


class TestLongShortRatios:
    _LS_RECORD = {
        "symbol": "BTCUSDT",
        "longShortRatio": "1.2500",
        "longAccount": "0.5556",
        "shortAccount": "0.4444",
        "timestamp": 1700000000000,
    }

    def test_long_short_ratio(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[self._LS_RECORD]):
            df = source.fetch(
                DataType.LONG_SHORT_RATIO, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.LONG_SHORT_RATIO.columns
        assert df["long_short_ratio"].iloc[0] == pytest.approx(1.25)

    def test_top_ls_accounts(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[self._LS_RECORD]):
            df = source.fetch(
                DataType.TOP_LS_ACCOUNTS, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1

    def test_top_ls_positions(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[self._LS_RECORD]):
            df = source.fetch(
                DataType.TOP_LS_POSITIONS, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1


# ------------------------------------------------------------------ #
#  Taker Buy/Sell Ratio                                                 #
# ------------------------------------------------------------------ #


class TestTakerBuySell:
    def test_fetch_taker_buy_sell(self):
        source = BinanceFuturesSource(rate_limit_sleep=0)
        raw = [
            {
                "buySellRatio": "1.1200",
                "buyVol": "5600.000",
                "sellVol": "5000.000",
                "timestamp": 1700000000000,
            },
        ]

        with patch.object(source._http, "get", return_value=raw):
            df = source.fetch(
                DataType.TAKER_BUY_SELL, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.TAKER_BUY_SELL.columns
        assert df["buy_sell_ratio"].iloc[0] == pytest.approx(1.12)
