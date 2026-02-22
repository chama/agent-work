"""Tests for market_data.infra.coinbase (CoinbaseSource)."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.coinbase import CoinbaseSource, _to_product_id


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_candle_row(base_time_s=1700000000, offset=0, granularity=60):
    """Create a single Coinbase candle row: [time, low, high, open, close, volume]."""
    t = base_time_s + offset * granularity
    return [t, 49000.0, 51000.0, 50000.0, 50500.0, 100.5]


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_coinbase_source(self):
        source = create_source("coinbase", rate_limit_sleep=0)
        assert source.exchange == "coinbase"

    def test_case_insensitive(self):
        source = create_source("Coinbase", rate_limit_sleep=0)
        assert source.exchange == "coinbase"


# ------------------------------------------------------------------ #
#  Symbol conversion                                                    #
# ------------------------------------------------------------------ #


class TestSymbolConversion:
    def test_btcusdt(self):
        assert _to_product_id("BTCUSDT") == "BTC-USDT"

    def test_btcusd(self):
        assert _to_product_id("BTCUSD") == "BTC-USD"

    def test_ethusdt(self):
        assert _to_product_id("ETHUSDT") == "ETH-USDT"

    def test_already_hyphenated(self):
        assert _to_product_id("BTC-USD") == "BTC-USD"

    def test_lowercase_input(self):
        assert _to_product_id("btcusdt") == "BTC-USDT"

    def test_unknown_quote_raises(self):
        with pytest.raises(ValueError, match="Cannot convert symbol"):
            _to_product_id("BTCEUR")


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = CoinbaseSource(rate_limit_sleep=0)
        # Coinbase returns descending order
        raw_data = [_make_candle_row(offset=i) for i in range(2, -1, -1)]

        with patch.object(source._http, "get", side_effect=[raw_data, []]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns
        assert df["open"].dtype == float
        assert df["high"].dtype == float
        assert df["low"].dtype == float
        assert df["close"].dtype == float
        assert df["volume"].dtype == float

    def test_ascending_sort(self):
        """Coinbase returns descending; output must be ascending."""
        source = CoinbaseSource(rate_limit_sleep=0)
        raw_data = [_make_candle_row(offset=i) for i in range(2, -1, -1)]

        with patch.object(source._http, "get", side_effect=[raw_data, []]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        timestamps = df["timestamp"].tolist()
        assert timestamps == sorted(timestamps)

    def test_column_mapping(self):
        """Coinbase column order [time, low, high, open, close, vol] is mapped correctly."""
        source = CoinbaseSource(rate_limit_sleep=0)
        # [time, low, high, open, close, volume]
        raw_data = [[1700000000, 100.0, 200.0, 150.0, 175.0, 50.0]]

        with patch.object(source._http, "get", side_effect=[raw_data, []]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert df["open"].iloc[0] == 150.0
        assert df["high"].iloc[0] == 200.0
        assert df["low"].iloc[0] == 100.0
        assert df["close"].iloc[0] == 175.0
        assert df["volume"].iloc[0] == 50.0

    def test_missing_fields_filled(self):
        """Fields not provided by Coinbase should be NaN or 0."""
        source = CoinbaseSource(rate_limit_sleep=0)
        raw_data = [_make_candle_row()]

        with patch.object(source._http, "get", side_effect=[raw_data, []]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert pd.isna(df["close_time"].iloc[0])
        assert np.isnan(df["quote_volume"].iloc[0])
        assert df["trades"].iloc[0] == 0
        assert np.isnan(df["taker_buy_volume"].iloc[0])
        assert np.isnan(df["taker_buy_quote_volume"].iloc[0])

    def test_empty_response(self):
        source = CoinbaseSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[]):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_unsupported_interval_raises(self):
        source = CoinbaseSource(rate_limit_sleep=0)

        with pytest.raises(ValueError, match="Unsupported interval"):
            source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="3m",
            )

    def test_unsupported_datatype_raises(self):
        source = CoinbaseSource(rate_limit_sleep=0)

        with pytest.raises(KeyError):
            source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )


# ------------------------------------------------------------------ #
#  Pagination                                                           #
# ------------------------------------------------------------------ #


class TestPagination:
    def test_multiple_pages(self):
        source = CoinbaseSource(rate_limit_sleep=0)
        batch1 = [_make_candle_row(offset=i) for i in range(2, -1, -1)]
        batch2 = [_make_candle_row(offset=i) for i in range(5, 2, -1)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return batch1
            if call_count == 2:
                return batch2
            return []

        with patch.object(source._http, "get", side_effect=mock_get):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert call_count >= 2
        assert len(df) == 6
