"""Tests for market_data.infra.kraken (KrakenFuturesSource)."""

from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.kraken import KrakenFuturesSource


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_spot_ohlc_response(pair="XXBTZUSD", rows=None, last=0):
    """Build a Kraken Spot OHLC API response."""
    if rows is None:
        rows = []
    return {
        "error": [],
        "result": {
            pair: rows,
            "last": last,
        },
    }


def _make_ohlc_row(ts_seconds=1700000000, offset=0):
    """Create a single Kraken OHLC row.

    Format: [timestamp, open, high, low, close, vwap, volume, count]
    """
    t = ts_seconds + offset * 60
    return [
        t, "50000.00", "51000.00", "49000.00", "50500.00",
        "50250.00", "100.500", 1234,
    ]


def _make_futures_funding_response(rates=None):
    """Build a Kraken Futures historicalfundingrates API response."""
    return {
        "result": "success",
        "rates": rates or [],
    }


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_kraken_source(self):
        source = create_source("kraken", rate_limit_sleep=0)
        assert source.exchange == "kraken"

    def test_case_insensitive(self):
        source = create_source("Kraken", rate_limit_sleep=0)
        assert source.exchange == "kraken"

    def test_unsupported_datatype_raises(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        with pytest.raises(KeyError):
            source.fetch(
                DataType.OPEN_INTEREST, "BTCUSD",
                "2024-01-01", "2024-01-02",
            )


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        rows = [_make_ohlc_row(offset=i) for i in range(3)]
        mock_response = _make_spot_ohlc_response(rows=rows, last=rows[-1][0])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns
        assert df["open"].dtype == float
        assert df["trades"].dtype == int

    def test_nan_columns(self):
        """Kraken doesn't provide close_time, quote_volume, etc."""
        source = KrakenFuturesSource(rate_limit_sleep=0)
        rows = [_make_ohlc_row()]
        mock_response = _make_spot_ohlc_response(rows=rows, last=rows[0][0])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert pd.isna(df["close_time"].iloc[0])
        assert pd.isna(df["quote_volume"].iloc[0])
        assert pd.isna(df["taker_buy_volume"].iloc[0])
        assert pd.isna(df["taker_buy_quote_volume"].iloc[0])

    def test_empty_response(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        mock_response = _make_spot_ohlc_response(rows=[], last=0)

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_timestamp_is_utc_datetime(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        rows = [_make_ohlc_row()]
        mock_response = _make_spot_ohlc_response(rows=rows, last=rows[0][0])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert str(df["timestamp"].dtype).startswith("datetime64[")

    def test_unsupported_interval_raises(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="Unsupported interval"):
            source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="3m",
            )

    def test_pagination(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)

        # Use timestamps within [2024-01-01, 2024-01-02) range
        base_ts = 1704067200  # 2024-01-01 00:00:00 UTC

        # First batch: 3 rows, last advances
        rows1 = [_make_ohlc_row(ts_seconds=base_ts, offset=i) for i in range(3)]
        resp1 = _make_spot_ohlc_response(rows=rows1, last=rows1[-1][0] + 60)

        # Second batch: 2 rows, last doesn't advance (end of data)
        rows2 = [_make_ohlc_row(ts_seconds=base_ts, offset=i + 3) for i in range(2)]
        resp2 = _make_spot_ohlc_response(rows=rows2, last=rows2[-1][0])

        # Third call: empty → signals end of data
        resp_empty = _make_spot_ohlc_response(rows=[], last=0)

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return resp1
            elif call_count == 2:
                return resp2
            return resp_empty

        with patch.object(source._http, "get", side_effect=mock_get):
            df = source.fetch(
                DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert call_count >= 2
        assert len(df) == 5


# ------------------------------------------------------------------ #
#  Funding Rate                                                         #
# ------------------------------------------------------------------ #


class TestFundingRate:
    def test_fetch_funding_rate(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        mock_response = _make_futures_funding_response(rates=[
            {
                "timestamp": "2024-01-01T00:00:00.000Z",
                "fundingRate": 0.0001,
                "relativeFundingRate": 0.0001,
            },
            {
                "timestamp": "2024-01-01T08:00:00.000Z",
                "fundingRate": -0.00005,
                "relativeFundingRate": -0.00005,
            },
        ])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "PF_XBTUSD",
                "2024-01-01", "2024-01-02",
            )

        assert len(df) == 2
        assert list(df.columns) == DataType.FUNDING_RATE.columns
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0001)
        assert df["symbol"].iloc[0] == "PF_XBTUSD"
        assert pd.isna(df["mark_price"].iloc[0])

    def test_empty(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        mock_response = _make_futures_funding_response(rates=[])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "PF_XBTUSD",
                "2024-01-01", "2024-01-02",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_filters_by_time_range(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        mock_response = _make_futures_funding_response(rates=[
            {
                "timestamp": "2023-12-31T16:00:00.000Z",
                "fundingRate": 0.0001,
                "relativeFundingRate": 0.0001,
            },
            {
                "timestamp": "2024-01-01T00:00:00.000Z",
                "fundingRate": 0.0002,
                "relativeFundingRate": 0.0002,
            },
            {
                "timestamp": "2024-01-02T08:00:00.000Z",
                "fundingRate": 0.0003,
                "relativeFundingRate": 0.0003,
            },
        ])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "PF_XBTUSD",
                "2024-01-01", "2024-01-02",
            )

        # Only the middle record is within [2024-01-01, 2024-01-02)
        assert len(df) == 1
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0002)

    def test_timestamp_is_utc_datetime(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        mock_response = _make_futures_funding_response(rates=[
            {
                "timestamp": "2024-01-01T00:00:00.000Z",
                "fundingRate": 0.0001,
                "relativeFundingRate": 0.0001,
            },
        ])

        with patch.object(source._http, "get", return_value=mock_response):
            df = source.fetch(
                DataType.FUNDING_RATE, "PF_XBTUSD",
                "2024-01-01", "2024-01-02",
            )

        assert str(df["timestamp"].dtype).startswith("datetime64[")


# ------------------------------------------------------------------ #
#  Spot / Futures API error handling                                    #
# ------------------------------------------------------------------ #


class TestApiErrors:
    def test_spot_api_error(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        error_response = {"error": ["EGeneral:Invalid arguments"], "result": {}}

        with patch.object(source._http, "get", return_value=error_response):
            with pytest.raises(RuntimeError, match="Kraken API error"):
                source.fetch(
                    DataType.OHLCV, "BTCUSD", "2024-01-01", "2024-01-02",
                    interval="1h",
                )

    def test_futures_api_error(self):
        source = KrakenFuturesSource(rate_limit_sleep=0)
        error_response = {"result": "error", "error": "some error"}

        with patch.object(source._http, "get", return_value=error_response):
            with pytest.raises(RuntimeError, match="Kraken Futures API error"):
                source.fetch(
                    DataType.FUNDING_RATE, "PF_XBTUSD",
                    "2024-01-01", "2024-01-02",
                )
