"""Tests for market_data.infra.phemex (PhemexFuturesSource)."""

import math
from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.phemex import PhemexFuturesSource


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_kline_row(ts_seconds=1740002400, offset=0, resolution=3600):
    """Create a single Phemex kline row for testing.

    Row format: [ts, interval, lastClose, open, high, low, close,
                 volume, turnover, symbol]
    """
    t = ts_seconds + offset * resolution
    return [
        t, resolution,
        "96264.4",   # lastClose
        "96271.2",   # open
        "96576.5",   # high
        "96264.4",   # low
        "96501.3",   # close
        "45.444",    # volume
        "4382684.8501",  # turnover (quote_volume)
        "BTCUSDT",   # symbol
    ]


def _make_funding_row(ts_ms=1740009600000, offset=0):
    """Create a single Phemex funding rate row for testing."""
    return {
        "symbol": ".BTCUSDTFR8H",
        "fundingRate": "0.0000399",
        "fundingTime": ts_ms + offset * 28800000,
        "intervalSeconds": 28800,
    }


def _api_response(rows, code=0):
    """Wrap rows in a Phemex API response envelope."""
    return {
        "code": code,
        "msg": "OK",
        "data": {"rows": rows},
    }


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_phemex_source(self):
        source = create_source("phemex", rate_limit_sleep=0)
        assert source.exchange == "phemex"

    def test_case_insensitive(self):
        source = create_source("Phemex", rate_limit_sleep=0)
        assert source.exchange == "phemex"


# ------------------------------------------------------------------ #
#  Unsupported DataType                                                 #
# ------------------------------------------------------------------ #


class TestUnsupported:
    def test_unsupported_data_type_raises(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="does not support"):
            source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT",
                "2024-01-01", "2024-01-02", period="1h",
            )


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        raw_rows = [_make_kline_row(offset=i) for i in range(3)]
        resp = _api_response(raw_rows)

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns

    def test_ohlcv_dtypes(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([_make_kline_row()])

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert df["open"].dtype == float
        assert df["volume"].dtype == float
        assert df["quote_volume"].dtype == float
        assert str(df["timestamp"].dtype).startswith("datetime64[")

    def test_ohlcv_values(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([_make_kline_row()])

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert df["open"].iloc[0] == pytest.approx(96271.2)
        assert df["high"].iloc[0] == pytest.approx(96576.5)
        assert df["low"].iloc[0] == pytest.approx(96264.4)
        assert df["close"].iloc[0] == pytest.approx(96501.3)
        assert df["volume"].iloc[0] == pytest.approx(45.444)
        assert df["quote_volume"].iloc[0] == pytest.approx(4382684.8501)
        assert df["trades"].iloc[0] == 0
        assert math.isnan(df["taker_buy_volume"].iloc[0])
        assert math.isnan(df["taker_buy_quote_volume"].iloc[0])

    def test_empty_response(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([])

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_pagination(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        batch1 = [_make_kline_row(offset=i) for i in range(3)]
        batch2 = [_make_kline_row(offset=i + 3) for i in range(2)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _api_response(batch1)
            if call_count == 2:
                return _api_response(batch2)
            return _api_response([])

        # end_time covers exactly 5 hours so pagination stops after batch2
        with patch.object(source._http, "get", side_effect=mock_get):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT",
                1740002400000, 1740002400000 + 5 * 3600 * 1000,
                interval="1h",
            )

        assert call_count == 2
        assert len(df) == 5

    def test_interval_required(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="interval is required"):
            source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

    def test_unsupported_interval(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="Unsupported interval"):
            source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="3m",
            )

    def test_interval_to_resolution_mapping(self):
        """Verify seconds are sent to the API, not the interval string."""
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([_make_kline_row()])
        captured_params = {}

        def mock_get(url, params):
            captured_params.update(params)
            return resp

        with patch.object(source._http, "get", side_effect=mock_get):
            source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="4h",
            )

        assert captured_params["resolution"] == 14400


# ------------------------------------------------------------------ #
#  Funding Rate                                                         #
# ------------------------------------------------------------------ #


class TestFundingRate:
    def test_fetch_funding_rate(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        raw_rows = [_make_funding_row(offset=i) for i in range(3)]
        resp = _api_response(raw_rows)

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT",
                "2024-01-01", "2024-01-02",
            )

        assert len(df) == 3
        assert list(df.columns) == DataType.FUNDING_RATE.columns
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0000399)
        assert df["symbol"].iloc[0] == "BTCUSDT"

    def test_mark_price_is_nan(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([_make_funding_row()])

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT",
                "2024-01-01", "2024-01-02",
            )

        assert math.isnan(df["mark_price"].iloc[0])

    def test_funding_rate_symbol_mapping(self):
        """Verify .{symbol}FR8H is sent to the API."""
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([_make_funding_row()])
        captured_params = {}

        def mock_get(url, params):
            captured_params.update(params)
            return resp

        with patch.object(source._http, "get", side_effect=mock_get):
            source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT",
                "2024-01-01", "2024-01-02",
            )

        assert captured_params["symbol"] == ".BTCUSDTFR8H"

    def test_empty(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        resp = _api_response([])

        with patch.object(source._http, "get", return_value=resp):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT",
                "2024-01-01", "2024-01-02",
            )

        assert len(df) == 0

    def test_funding_rate_pagination(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        batch1 = [_make_funding_row(offset=i) for i in range(100)]
        batch2 = [_make_funding_row(offset=i + 100) for i in range(10)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _api_response(batch1)
            return _api_response(batch2)

        with patch.object(source._http, "get", side_effect=mock_get):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT",
                0, 1800000000000,
            )

        assert call_count == 2
        assert len(df) == 110


# ------------------------------------------------------------------ #
#  API Error Handling                                                    #
# ------------------------------------------------------------------ #


class TestApiError:
    def test_api_error_raises(self):
        source = PhemexFuturesSource(rate_limit_sleep=0)
        error_resp = {"code": 30018, "msg": "phemex.data.size.uplimt", "data": None}

        with patch.object(source._http, "get", return_value=error_resp):
            with pytest.raises(RuntimeError, match="Phemex API error 30018"):
                source.fetch(
                    DataType.OHLCV, "BTCUSDT",
                    "2024-01-01", "2024-01-02",
                    interval="1h",
                )
