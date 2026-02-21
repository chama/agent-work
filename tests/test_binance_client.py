"""Tests for binance_client package."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from binance_client.base import BinanceBaseClient, to_milliseconds
from binance_client.futures import BinanceFuturesClient


# ------------------------------------------------------------------ #
#  to_milliseconds                                                     #
# ------------------------------------------------------------------ #


class TestToMilliseconds:
    def test_int_passthrough(self):
        assert to_milliseconds(1700000000000) == 1700000000000

    def test_float_truncated(self):
        assert to_milliseconds(1700000000000.5) == 1700000000000

    def test_date_string(self):
        # 2024-01-01 00:00:00 UTC
        ms = to_milliseconds("2024-01-01")
        expected = int(
            datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
        )
        assert ms == expected

    def test_datetime_string(self):
        ms = to_milliseconds("2024-01-01 12:30:00")
        expected = int(
            datetime(2024, 1, 1, 12, 30, 0, tzinfo=timezone.utc).timestamp()
            * 1000
        )
        assert ms == expected

    def test_datetime_object_naive(self):
        dt = datetime(2024, 6, 15, 10, 0, 0)
        ms = to_milliseconds(dt)
        expected = int(
            dt.replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        assert ms == expected

    def test_datetime_object_aware(self):
        dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        ms = to_milliseconds(dt)
        assert ms == int(dt.timestamp() * 1000)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Unsupported datetime format"):
            to_milliseconds("not-a-date")

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Cannot convert"):
            to_milliseconds([1, 2, 3])


# ------------------------------------------------------------------ #
#  BinanceBaseClient                                                   #
# ------------------------------------------------------------------ #


class TestBinanceBaseClient:
    def test_successful_request(self):
        client = BinanceBaseClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"test": "data"}]

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client._request("https://example.com/api")
            assert result == [{"test": "data"}]

    def test_retry_on_429(self):
        client = BinanceBaseClient(max_retries=3, rate_limit_sleep=0)

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.text = "Too many requests"

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {"ok": True}

        with patch.object(
            client.session, "get", side_effect=[rate_limited, success]
        ), patch("binance_client.base.time.sleep"):
            result = client._request("https://example.com/api")
            assert result == {"ok": True}

    def test_raises_on_server_error(self):
        client = BinanceBaseClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                client._request("https://example.com/api")

    def test_raises_on_ip_ban(self):
        client = BinanceBaseClient(rate_limit_sleep=0)
        mock_resp = MagicMock()
        mock_resp.status_code = 418
        mock_resp.text = "IP banned"

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="IP banned"):
                client._request("https://example.com/api")

    def test_context_manager(self):
        with BinanceBaseClient() as client:
            assert client.session is not None


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - klines                                       #
# ------------------------------------------------------------------ #


def _make_kline_row(open_time_ms=1700000000000, offset=0):
    """Create a single kline data row for testing."""
    t = open_time_ms + offset * 60000
    return [
        t,                    # open_time
        "50000.00",           # open
        "51000.00",           # high
        "49000.00",           # low
        "50500.00",           # close
        "100.500",            # volume
        t + 59999,            # close_time
        "5050000.00",         # quote_volume
        1234,                 # trades
        "60.300",             # taker_buy_volume
        "3030000.00",         # taker_buy_quote_volume
        "0",                  # ignore
    ]


class TestBinanceFuturesClientKlines:
    def test_get_klines_returns_dataframe(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw_data = [_make_kline_row(offset=i) for i in range(3)]

        with patch.object(client, "_request", return_value=raw_data):
            df = client.get_klines("BTCUSDT", "1m", "2024-01-01", "2024-01-02")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == [
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_volume", "taker_buy_quote_volume",
        ]
        assert df["open"].dtype == float
        assert df["trades"].dtype == int
        assert str(df["timestamp"].dtype).startswith("datetime64[")

    def test_get_klines_empty_response(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)

        with patch.object(client, "_request", return_value=[]):
            df = client.get_klines("BTCUSDT", "1h", "2024-01-01", "2024-01-02")

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_get_klines_pagination(self):
        """When first batch returns `limit` rows, client should paginate."""
        client = BinanceFuturesClient(rate_limit_sleep=0)
        batch1 = [_make_kline_row(offset=i) for i in range(3)]
        batch2 = [_make_kline_row(offset=i + 3) for i in range(2)]

        call_count = 0

        def mock_request(url, params):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return batch1
            return batch2

        with patch.object(client, "_request", side_effect=mock_request):
            df = client.get_klines(
                "BTCUSDT", "1m", "2024-01-01", "2024-01-02", limit=3
            )

        assert len(df) == 5
        assert call_count == 2


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - index/mark price klines                      #
# ------------------------------------------------------------------ #


class TestIndexMarkPriceKlines:
    def test_index_price_klines_columns(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_index_price_klines(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        # include_extra=False → only OHLC columns
        assert list(df.columns) == ["timestamp", "open", "high", "low", "close"]

    def test_mark_price_klines_columns(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [_make_kline_row(offset=0)]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_mark_price_klines(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert list(df.columns) == ["timestamp", "open", "high", "low", "close"]


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - funding rate                                  #
# ------------------------------------------------------------------ #


class TestFundingRate:
    def test_get_funding_rate_history(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
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

        with patch.object(client, "_request", return_value=raw):
            df = client.get_funding_rate_history(
                "BTCUSDT", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 2
        assert list(df.columns) == [
            "timestamp", "symbol", "funding_rate", "mark_price"
        ]
        assert df["funding_rate"].iloc[0] == pytest.approx(0.0001)
        assert df["funding_rate"].iloc[1] == pytest.approx(-0.00005)

    def test_get_funding_rate_empty(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)

        with patch.object(client, "_request", return_value=[]):
            df = client.get_funding_rate_history(
                "BTCUSDT", "2024-01-01", "2024-01-02"
            )

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - open interest history                         #
# ------------------------------------------------------------------ #


class TestOpenInterestHistory:
    def test_get_open_interest_history(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [
            {
                "symbol": "BTCUSDT",
                "sumOpenInterest": "12345.678",
                "sumOpenInterestValue": "617283900.00",
                "timestamp": 1700000000000,
            },
        ]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_open_interest_history(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 1
        assert list(df.columns) == [
            "timestamp", "symbol", "open_interest", "open_interest_value"
        ]
        assert df["open_interest"].iloc[0] == pytest.approx(12345.678)


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - long/short ratios                             #
# ------------------------------------------------------------------ #


class TestLongShortRatios:
    def _make_ls_record(self, ts=1700000000000):
        return {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.2500",
            "longAccount": "0.5556",
            "shortAccount": "0.4444",
            "timestamp": ts,
        }

    def test_get_long_short_ratio(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [self._make_ls_record()]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_long_short_ratio(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 1
        assert "long_short_ratio" in df.columns
        assert df["long_short_ratio"].iloc[0] == pytest.approx(1.25)

    def test_get_top_trader_accounts(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [self._make_ls_record()]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_top_trader_long_short_ratio_accounts(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 1

    def test_get_top_trader_positions(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [self._make_ls_record()]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_top_trader_long_short_ratio_positions(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 1


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - taker buy/sell ratio                          #
# ------------------------------------------------------------------ #


class TestTakerBuySellRatio:
    def test_get_taker_buy_sell_ratio(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [
            {
                "buySellRatio": "1.1200",
                "buyVol": "5600.000",
                "sellVol": "5000.000",
                "timestamp": 1700000000000,
            },
        ]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_taker_buy_sell_ratio(
                "BTCUSDT", "1h", "2024-01-01", "2024-01-02"
            )

        assert len(df) == 1
        assert list(df.columns) == [
            "timestamp", "buy_sell_ratio", "buy_vol", "sell_vol"
        ]
        assert df["buy_sell_ratio"].iloc[0] == pytest.approx(1.12)


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - aggregated trades                             #
# ------------------------------------------------------------------ #


class TestAggTrades:
    def test_get_agg_trades(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = [
            {
                "a": 100,
                "p": "50000.00",
                "q": "0.500",
                "f": 200,
                "l": 201,
                "T": 1700000000000,
                "m": True,
            },
        ]

        with patch.object(client, "_request", return_value=raw):
            df = client.get_agg_trades(
                "BTCUSDT",
                1700000000000,
                1700000000000 + 3600000,
            )

        assert len(df) == 1
        assert list(df.columns) == [
            "timestamp", "agg_trade_id", "price", "quantity",
            "first_trade_id", "last_trade_id", "is_buyer_maker",
        ]
        assert df["price"].iloc[0] == pytest.approx(50000.0)


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - exchange info / symbols                       #
# ------------------------------------------------------------------ #


class TestExchangeInfo:
    def test_get_futures_symbols(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        mock_info = {
            "symbols": [
                {"symbol": "BTCUSDT", "status": "TRADING", "quoteAsset": "USDT"},
                {"symbol": "ETHUSDT", "status": "TRADING", "quoteAsset": "USDT"},
                {"symbol": "BTCBUSD", "status": "TRADING", "quoteAsset": "BUSD"},
                {"symbol": "XRPUSDT", "status": "BREAK", "quoteAsset": "USDT"},
            ]
        }

        with patch.object(client, "_request", return_value=mock_info):
            symbols = client.get_futures_symbols()

        assert symbols == ["BTCUSDT", "ETHUSDT"]


# ------------------------------------------------------------------ #
#  BinanceFuturesClient - snapshot endpoints                            #
# ------------------------------------------------------------------ #


class TestSnapshotEndpoints:
    def test_get_ticker_24hr_single(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = {
            "symbol": "BTCUSDT",
            "priceChange": "-100.50",
            "priceChangePercent": "-0.200",
            "weightedAvgPrice": "50000.00",
            "lastPrice": "50100.00",
            "lastQty": "1.000",
            "openPrice": "50200.50",
            "highPrice": "51000.00",
            "lowPrice": "49500.00",
            "volume": "25000.000",
            "quoteVolume": "1250000000.00",
        }

        with patch.object(client, "_request", return_value=raw):
            df = client.get_ticker_24hr("BTCUSDT")

        assert len(df) == 1
        assert df["lastPrice"].iloc[0] == pytest.approx(50100.0)

    def test_get_premium_index(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = {
            "symbol": "BTCUSDT",
            "markPrice": "50000.00",
            "indexPrice": "49990.00",
            "estimatedSettlePrice": "49995.00",
            "lastFundingRate": "0.00010000",
            "interestRate": "0.00010000",
            "nextFundingTime": 1700028800000,
            "time": 1700000000000,
        }

        with patch.object(client, "_request", return_value=raw):
            df = client.get_premium_index("BTCUSDT")

        assert len(df) == 1
        assert df["markPrice"].iloc[0] == pytest.approx(50000.0)
        assert str(df["time"].dtype).startswith("datetime64[")

    def test_get_book_depth(self):
        client = BinanceFuturesClient(rate_limit_sleep=0)
        raw = {
            "bids": [["50000.00", "1.500"], ["49999.00", "2.000"]],
            "asks": [["50001.00", "1.200"], ["50002.00", "3.000"]],
        }

        with patch.object(client, "_request", return_value=raw):
            result = client.get_book_depth("BTCUSDT", limit=5)

        assert "bids" in result
        assert "asks" in result
        assert len(result["bids"]) == 2
        assert result["bids"]["price"].iloc[0] == pytest.approx(50000.0)
