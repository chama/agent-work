"""Tests for market_data.infra.upbit (UpbitSource)."""

from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.upbit import UpbitSource, _to_upbit_market


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _make_candle(timestamp_ms=1704070800000, offset=0):
    """Create a single Upbit candle record for testing."""
    t = timestamp_ms + offset * 60000
    utc_str = pd.Timestamp(t, unit="ms", tz="UTC").strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    return {
        "market": "KRW-BTC",
        "candle_date_time_utc": utc_str,
        "opening_price": 50000000,
        "high_price": 51000000,
        "low_price": 49000000,
        "trade_price": 50500000,
        "timestamp": t,
        "candle_acc_trade_price": 1234567890,
        "candle_acc_trade_volume": 123.456,
    }


# ------------------------------------------------------------------ #
#  Symbol Conversion                                                    #
# ------------------------------------------------------------------ #


class TestSymbolConversion:
    def test_btc_usdt(self):
        assert _to_upbit_market("BTCUSDT") == "USDT-BTC"

    def test_btc_krw(self):
        assert _to_upbit_market("BTCKRW") == "KRW-BTC"

    def test_eth_btc(self):
        assert _to_upbit_market("ETHBTC") == "BTC-ETH"

    def test_already_upbit_format(self):
        assert _to_upbit_market("KRW-BTC") == "KRW-BTC"

    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError, match="Cannot parse symbol"):
            _to_upbit_market("INVALID")


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_upbit_source(self):
        source = create_source("upbit", rate_limit_sleep=0)
        assert source.exchange == "upbit"

    def test_case_insensitive(self):
        source = create_source("Upbit", rate_limit_sleep=0)
        assert source.exchange == "upbit"


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = UpbitSource(rate_limit_sleep=0)
        raw_data = [_make_candle(offset=i) for i in range(3)]

        with patch.object(source._http, "get", return_value=raw_data):
            df = source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == DataType.OHLCV.columns
        assert df["open"].dtype == float
        assert df["close"].dtype == float
        assert df["volume"].dtype == float
        assert df["quote_volume"].dtype == float

    def test_empty_response(self):
        source = UpbitSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=[]):
            df = source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_symbol_conversion_in_fetch(self):
        source = UpbitSource(rate_limit_sleep=0)
        raw_data = [_make_candle()]

        with patch.object(source._http, "get", return_value=raw_data) as mock_get:
            source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1d",
            )

        # Verify the market param was converted to Upbit format
        call_args = mock_get.call_args
        params = call_args[0][1]  # positional: (url, params_dict)
        assert params["market"] == "USDT-BTC"

    def test_unsupported_interval_raises(self):
        source = UpbitSource(rate_limit_sleep=0)

        with pytest.raises(ValueError, match="Unsupported interval"):
            source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="2h",
            )

    def test_missing_interval_raises(self):
        source = UpbitSource(rate_limit_sleep=0)

        with pytest.raises(ValueError, match="interval is required"):
            source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
            )

    def test_pagination(self):
        source = UpbitSource(rate_limit_sleep=0)
        # First batch: 3 candles (equals count, triggers next page)
        batch1 = [_make_candle(timestamp_ms=1704072000000, offset=-i) for i in range(3)]
        # Second batch: 2 candles (less than count, stops)
        batch2 = [_make_candle(timestamp_ms=1704070800000, offset=-i) for i in range(2)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            return batch1 if call_count == 1 else batch2

        with patch.object(source._http, "get", side_effect=mock_get):
            source._paginate_candles(
                "/candles/minutes/1",
                "KRW-BTC",
                start_ms=0,
                end_ms=1704080000000,
                count=3,
            )

        assert call_count == 2

    def test_ohlcv_sorted_by_timestamp(self):
        source = UpbitSource(rate_limit_sleep=0)
        # Upbit returns newest first, our output should be sorted ascending
        raw_data = [_make_candle(offset=2), _make_candle(offset=0), _make_candle(offset=1)]

        with patch.object(source._http, "get", return_value=raw_data):
            df = source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert df["timestamp"].is_monotonic_increasing

    def test_unavailable_columns_have_expected_values(self):
        source = UpbitSource(rate_limit_sleep=0)
        raw_data = [_make_candle()]

        with patch.object(source._http, "get", return_value=raw_data):
            df = source.fetch(
                DataType.OHLCV, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="1m",
            )

        assert df["trades"].iloc[0] == 0
        assert pd.isna(df["taker_buy_volume"].iloc[0])
        assert pd.isna(df["taker_buy_quote_volume"].iloc[0])
        assert df["quote_volume"].iloc[0] == 1234567890


# ------------------------------------------------------------------ #
#  Unsupported DataTypes                                                #
# ------------------------------------------------------------------ #


class TestUnsupportedDataTypes:
    @pytest.mark.parametrize("data_type", [
        DataType.FUNDING_RATE,
        DataType.OPEN_INTEREST,
        DataType.LONG_SHORT_RATIO,
        DataType.TOP_LS_ACCOUNTS,
        DataType.TOP_LS_POSITIONS,
        DataType.TAKER_BUY_SELL,
        DataType.INDEX_PRICE,
        DataType.MARK_PRICE,
    ])
    def test_unsupported_data_type_raises_key_error(self, data_type):
        source = UpbitSource(rate_limit_sleep=0)

        with pytest.raises(KeyError, match="does not support"):
            source.fetch(
                data_type, "BTCKRW", "2024-01-01", "2024-01-02",
                interval="1h",
                period="1h",
            )
