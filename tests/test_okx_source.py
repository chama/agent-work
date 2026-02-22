"""Tests for market_data.infra.okx (OkxFuturesSource)."""

from unittest.mock import patch

import pandas as pd
import pytest

from market_data import DataType, create_source
from market_data.infra.okx import (
    OkxFuturesSource,
    _convert_bar,
    _to_ccy,
    _to_index_inst_id,
    _to_inst_id,
)


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #


def _okx_resp(data: list) -> dict:
    """Wrap data in OKX response envelope."""
    return {"code": "0", "msg": "", "data": data}


def _make_kline_row(open_time_ms: int = 1700000000000, offset: int = 0) -> list[str]:
    """Create a single OKX kline row (all string values)."""
    t = open_time_ms + offset * 60000
    return [
        str(t), "50000.00", "51000.00", "49000.00", "50500.00",
        "100.500", "5050000.00", "5050000000.00", "1",
    ]


# ------------------------------------------------------------------ #
#  Factory                                                              #
# ------------------------------------------------------------------ #


class TestFactory:
    def test_create_okx_source(self):
        source = create_source("okx", rate_limit_sleep=0)
        assert source.exchange == "okx"

    def test_case_insensitive(self):
        source = create_source("OKX", rate_limit_sleep=0)
        assert source.exchange == "okx"


# ------------------------------------------------------------------ #
#  Symbol / interval conversion                                         #
# ------------------------------------------------------------------ #


class TestSymbolConversion:
    def test_btcusdt_to_inst_id(self):
        assert _to_inst_id("BTCUSDT") == "BTC-USDT-SWAP"

    def test_ethusdt_to_inst_id(self):
        assert _to_inst_id("ETHUSDT") == "ETH-USDT-SWAP"

    def test_btcusd_to_inst_id(self):
        assert _to_inst_id("BTCUSD") == "BTC-USD-SWAP"

    def test_index_inst_id(self):
        assert _to_index_inst_id("BTCUSDT") == "BTC-USDT"

    def test_ccy(self):
        assert _to_ccy("BTCUSDT") == "BTC"

    def test_ccy_eth(self):
        assert _to_ccy("ETHUSDT") == "ETH"

    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError, match="Cannot convert"):
            _to_inst_id("INVALID")


class TestBarConversion:
    def test_1h(self):
        assert _convert_bar("1h") == "1H"

    def test_4h(self):
        assert _convert_bar("4h") == "4H"

    def test_1d(self):
        assert _convert_bar("1d") == "1D"

    def test_1w(self):
        assert _convert_bar("1w") == "1W"

    def test_1m_unchanged(self):
        assert _convert_bar("1m") == "1m"

    def test_15m_unchanged(self):
        assert _convert_bar("15m") == "15m"

    def test_1M_unchanged(self):
        assert _convert_bar("1M") == "1M"


# ------------------------------------------------------------------ #
#  OHLCV                                                                #
# ------------------------------------------------------------------ #


class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        raw_data = [_make_kline_row(offset=i) for i in range(3)]

        with patch.object(source._http, "get", return_value=_okx_resp(raw_data)):
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
        source = OkxFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=_okx_resp([])):
            df = source.fetch(
                DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_pagination(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        batch1 = [_make_kline_row(offset=i) for i in range(3)]
        batch2 = [_make_kline_row(offset=i + 3) for i in range(2)]

        call_count = 0

        def mock_get(url, params):
            nonlocal call_count
            call_count += 1
            return _okx_resp(batch1 if call_count == 1 else batch2)

        with patch.object(source._http, "get", side_effect=mock_get):
            source._paginate_klines(
                "/api/v5/market/history-candles",
                {"instId": "BTC-USDT-SWAP", "bar": "1m"},
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
        source = OkxFuturesSource(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
            df = source.fetch(
                DataType.INDEX_PRICE, "BTCUSDT", "2024-01-01", "2024-01-02",
                interval="1h",
            )

        assert list(df.columns) == DataType.INDEX_PRICE.columns

    def test_mark_price_columns(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
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
        source = OkxFuturesSource(rate_limit_sleep=0)
        raw = [
            {
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "0.00010000",
                "realizedRate": "0.00009000",
                "fundingTime": "1700000000000",
            },
            {
                "instId": "BTC-USDT-SWAP",
                "fundingRate": "-0.00005000",
                "realizedRate": "-0.00004000",
                "fundingTime": "1700028800000",
            },
        ]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 2
        assert list(df.columns) == DataType.FUNDING_RATE.columns
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0001)
        # mark_price should be NaN (not available in OKX funding API)
        assert pd.isna(df["mark_price"].iloc[0])

    def test_empty(self):
        source = OkxFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=_okx_resp([])):
            df = source.fetch(
                DataType.FUNDING_RATE, "BTCUSDT", "2024-01-01", "2024-01-02",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Open Interest                                                        #
# ------------------------------------------------------------------ #


class TestOpenInterest:
    def test_fetch_open_interest(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        # OKX rubik: [[ts, oi, oiCcy], ...]
        raw = [
            ["1700000000000", "12345.678", "617283900.00"],
        ]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
            df = source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.OPEN_INTEREST.columns
        assert df["open_interest"].iloc[0] == pytest.approx(12345.678)

    def test_empty(self):
        source = OkxFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=_okx_resp([])):
            df = source.fetch(
                DataType.OPEN_INTEREST, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Long/Short Ratio                                                     #
# ------------------------------------------------------------------ #


class TestLongShortRatio:
    def test_fetch_long_short_ratio(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        # OKX rubik: [[ts, ratio], ...]
        raw = [
            ["1700000000000", "1.2500"],
        ]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
            df = source.fetch(
                DataType.LONG_SHORT_RATIO, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.LONG_SHORT_RATIO.columns
        assert df["long_short_ratio"].iloc[0] == pytest.approx(1.25)
        # ratio=1.25 → long = 1.25/2.25, short = 1/2.25
        assert df["long_account"].iloc[0] == pytest.approx(1.25 / 2.25)
        assert df["short_account"].iloc[0] == pytest.approx(1.0 / 2.25)

    def test_empty(self):
        source = OkxFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=_okx_resp([])):
            df = source.fetch(
                DataType.LONG_SHORT_RATIO, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Taker Buy/Sell Ratio                                                 #
# ------------------------------------------------------------------ #


class TestTakerBuySell:
    def test_fetch_taker_buy_sell(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        # OKX rubik: [[ts, sellVol, buyVol], ...]
        raw = [
            ["1700000000000", "5000.000", "5600.000"],
        ]

        with patch.object(source._http, "get", return_value=_okx_resp(raw)):
            df = source.fetch(
                DataType.TAKER_BUY_SELL, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 1
        assert list(df.columns) == DataType.TAKER_BUY_SELL.columns
        assert df["buy_sell_ratio"].iloc[0] == pytest.approx(5600.0 / 5000.0)
        assert df["buy_vol"].iloc[0] == pytest.approx(5600.0)
        assert df["sell_vol"].iloc[0] == pytest.approx(5000.0)

    def test_empty(self):
        source = OkxFuturesSource(rate_limit_sleep=0)

        with patch.object(source._http, "get", return_value=_okx_resp([])):
            df = source.fetch(
                DataType.TAKER_BUY_SELL, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

        assert len(df) == 0


# ------------------------------------------------------------------ #
#  Unsupported DataType                                                 #
# ------------------------------------------------------------------ #


class TestUnsupported:
    def test_top_ls_accounts_not_supported(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="does not support"):
            source.fetch(
                DataType.TOP_LS_ACCOUNTS, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )

    def test_top_ls_positions_not_supported(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        with pytest.raises(ValueError, match="does not support"):
            source.fetch(
                DataType.TOP_LS_POSITIONS, "BTCUSDT", "2024-01-01", "2024-01-02",
                period="1h",
            )


# ------------------------------------------------------------------ #
#  API error handling                                                   #
# ------------------------------------------------------------------ #


class TestApiError:
    def test_api_error_raises(self):
        source = OkxFuturesSource(rate_limit_sleep=0)
        error_resp = {"code": "50000", "msg": "Body can not be empty", "data": []}

        with patch.object(source._http, "get", return_value=error_resp):
            with pytest.raises(RuntimeError, match="OKX API error"):
                source.fetch(
                    DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02",
                    interval="1h",
                )
