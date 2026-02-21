"""Tests for market_data.infra.bybit (BybitFuturesSource)."""

from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.bybit import BybitFuturesSource


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _bybit_response(result):
    """Wrap result in Bybit API response envelope."""
    return {"retCode": 0, "retMsg": "OK", "result": result, "time": 1700000000000}


def _make_kline_row(start_time_ms=1700000000000, offset=0):
    """Create a single Bybit kline row: [startTime, O, H, L, C, volume, turnover]."""
    t = start_time_ms + offset * 60000
    return [
        str(t), "50000.00", "51000.00", "49000.00", "50500.00",
        "100.500", "5050000.00",
    ]


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_bybit_source(self):
        source = create_source("bybit", rate_limit_sleep=0)
        assert source.exchange == "bybit"

    def test_case_insensitive(self):
        source = create_source("Bybit", rate_limit_sleep=0)
        assert source.exchange == "bybit"


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        # Bybit returns descending order
        rows = [_make_kline_row(offset=2), _make_kline_row(offset=1), _make_kline_row(offset=0)]
        raw_response = _bybit_response({"list": rows})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns
        assert df["open"].dtype == float
        assert df["trades"].iloc[0] == 0  # Bybit doesn't provide trades

    def test_empty_response(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({"list": []})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_ascending_sort(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        # Descending order from Bybit
        rows = [_make_kline_row(offset=2), _make_kline_row(offset=1), _make_kline_row(offset=0)]
        raw_response = _bybit_response({"list": rows})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        timestamps = df["timestamp"].tolist()
        assert timestamps == sorted(timestamps)

    def test_pagination(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        # First batch: 3 items (descending)
        batch1 = _bybit_response({"list": [
            _make_kline_row(offset=5), _make_kline_row(offset=4), _make_kline_row(offset=3),
        ]})
        # Second batch: 2 items (descending)
        batch2 = _bybit_response({"list": [
            _make_kline_row(offset=2), _make_kline_row(offset=1),
        ]})

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            return batch1 if call_count == 1 else batch2

        with patch.object(source._http, "get", side_effect=mock_get):
            data = source._paginate_klines(
                "/v5/market/kline",
                {"category": "linear", "symbol": "BTCUSDT", "interval": "1"},
                1700000000000,
                1700000000000 + 600000,
                limit=3,
            )

        assert call_count == 2
        assert len(data) == 5
        # Verify ascending order after sort
        timestamps = [int(row[0]) for row in data]
        assert timestamps == sorted(timestamps)


# ------------------------------------------------------------------ #
#  Index / Mark Price Klines                                            #
# ------------------------------------------------------------------ #


class TestPriceKlines:
    def test_index_price_columns(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        rows = [_make_kline_row(offset=0)]
        raw_response = _bybit_response({"list": rows})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.INDEX_PRICE, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert list(df.columns) == DataType.INDEX_PRICE.columns

    def test_mark_price_columns(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        rows = [_make_kline_row(offset=0)]
        raw_response = _bybit_response({"list": rows})

        with patch.object(source._http, "get", return_value=raw_response):
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
        source = BybitFuturesSource(rate_limit_sleep=0)
        # Descending order from Bybit
        raw_response = _bybit_response({"list": [
            {
                "symbol": "BTCUSDT",
                "fundingRate": "0.00010000",
                "fundingRateTimestamp": "1700028800000",
            },
            {
                "symbol": "BTCUSDT",
                "fundingRate": "-0.00005000",
                "fundingRateTimestamp": "1700000000000",
            },
        ]})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 2
        assert list(df.columns) == DataType.FUNDING_RATE.columns
        # After ascending sort, older record comes first
        assert df["funding_rate"].iloc[0] == pytest.approx(-0.00005)
        assert pd.isna(df["mark_price"].iloc[0])  # Bybit doesn't provide mark_price

    def test_empty(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({"list": []})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Open Interest                                                        #
# ------------------------------------------------------------------ #


class TestOpenInterest:
    def test_fetch_open_interest(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({
            "list": [
                {
                    "openInterest": "12345.678",
                    "timestamp": "1700000000000",
                },
            ],
            "nextPageCursor": "",
        })

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.OPEN_INTEREST.columns
        assert df["open_interest"].iloc[0] == pytest.approx(12345.678)
        assert pd.isna(df["open_interest_value"].iloc[0])

    def test_empty(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({
            "list": [],
            "nextPageCursor": "",
        })

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 0

    def test_cursor_pagination(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        page1 = _bybit_response({
            "list": [
                {"openInterest": "100.0", "timestamp": "1700000000000"},
                {"openInterest": "200.0", "timestamp": "1700003600000"},
            ],
            "nextPageCursor": "abc123",
        })
        page2 = _bybit_response({
            "list": [
                {"openInterest": "300.0", "timestamp": "1700007200000"},
            ],
            "nextPageCursor": "",
        })

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            return page1 if call_count == 1 else page2

        with patch.object(source._http, "get", side_effect=mock_get):
            data = source._paginate_open_interest(
                "BTCUSDT", 1700000000000, 1700010000000, "1h", limit=2,
            )

        assert call_count == 2
        assert len(data) == 3


# ------------------------------------------------------------------ #
#  Long/Short Ratio                                                     #
# ------------------------------------------------------------------ #


class TestLongShortRatio:
    def test_fetch_long_short_ratio(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({"list": [
            {
                "symbol": "BTCUSDT",
                "buyRatio": "0.5556",
                "sellRatio": "0.4444",
                "timestamp": "1700000000000",
            },
        ]})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.LONG_SHORT_RATIO, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.LONG_SHORT_RATIO.columns
        assert df["long_account"].iloc[0] == pytest.approx(0.5556)
        assert df["short_account"].iloc[0] == pytest.approx(0.4444)
        assert df["long_short_ratio"].iloc[0] == pytest.approx(0.5556 / 0.4444)

    def test_empty(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        raw_response = _bybit_response({"list": []})

        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(
                DataType.LONG_SHORT_RATIO, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  API Error Handling                                                    #
# ------------------------------------------------------------------ #


class TestApiError:
    def test_retcode_error_raises(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        error_response = {"retCode": 10001, "retMsg": "Invalid parameter", "result": {}}

        with patch.object(source._http, "get", return_value=error_response):
            with pytest.raises(RuntimeError, match="Bybit API error"):
                source.fetch(
                    DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                    interval="1h",
                )

    def test_unsupported_data_type(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        with pytest.raises(NotImplementedError, match="does not support"):
            source.fetch(
                DataType.TAKER_BUY_SELL, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )
