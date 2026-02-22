"""OKX USDT-M Futures adapter implementing FuturesDataSource.

Maps OKX V5 API responses to the canonical DataType schemas
defined in the domain layer.
"""

import logging

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://www.okx.com"


# ------------------------------------------------------------------ #
#  Symbol / interval conversion helpers                                #
# ------------------------------------------------------------------ #


def _to_inst_id(symbol: str) -> str:
    """Convert standard symbol to OKX swap instrument ID.

    BTCUSDT → BTC-USDT-SWAP, BTCUSD → BTC-USD-SWAP
    """
    symbol = symbol.upper()
    for quote in ("USDT", "USD"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}-{quote}-SWAP"
    raise ValueError(f"Cannot convert symbol to OKX instId: {symbol!r}")


def _to_index_inst_id(symbol: str) -> str:
    """Convert standard symbol to OKX index instrument ID (no SWAP suffix).

    BTCUSDT → BTC-USDT
    """
    symbol = symbol.upper()
    for quote in ("USDT", "USD"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}-{quote}"
    raise ValueError(f"Cannot convert symbol to OKX index instId: {symbol!r}")


def _to_ccy(symbol: str) -> str:
    """Extract base currency from symbol.

    BTCUSDT → BTC
    """
    symbol = symbol.upper()
    for quote in ("USDT", "USD"):
        if symbol.endswith(quote):
            return symbol[: -len(quote)]
    raise ValueError(f"Cannot extract currency from symbol: {symbol!r}")


def _convert_bar(interval: str) -> str:
    """Convert standard interval to OKX bar format.

    OKX uses uppercase for hours/days/weeks: 1h→1H, 4h→4H, 1d→1D, 1w→1W.
    Minutes (1m, 5m, ...) and months (1M) are unchanged.
    """
    if not interval:
        return interval
    last = interval[-1]
    if last in ("h", "d", "w"):
        return interval[:-1] + last.upper()
    return interval


class OkxFuturesSource:
    """OKX USDT-M Futures data source.

    Implements the ``FuturesDataSource`` protocol.
    """

    def __init__(
        self,
        max_retries: int = 3,
        rate_limit_sleep: float = 0.1,
    ):
        self._http = HttpClient(
            max_retries=max_retries,
            rate_limit_sleep=rate_limit_sleep,
        )

    @property
    def exchange(self) -> str:
        return "okx"

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #
    #  Public: unified fetch entry point                                   #
    # ------------------------------------------------------------------ #

    def fetch(
        self,
        data_type: DataType,
        symbol: str,
        start_time: str | int,
        end_time: str | int,
        *,
        interval: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        dispatcher = {
            DataType.OHLCV: self._fetch_ohlcv,
            DataType.INDEX_PRICE: self._fetch_index_price,
            DataType.MARK_PRICE: self._fetch_mark_price,
            DataType.FUNDING_RATE: self._fetch_funding_rate,
            DataType.OPEN_INTEREST: self._fetch_open_interest,
            DataType.LONG_SHORT_RATIO: self._fetch_long_short_ratio,
            DataType.TAKER_BUY_SELL: self._fetch_taker_buy_sell,
        }
        handler = dispatcher.get(data_type)
        if handler is None:
            raise ValueError(
                f"OKX adapter does not support {data_type!r}"
            )
        return handler(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            period=period,
        )

    # ------------------------------------------------------------------ #
    #  Internal: OKX response wrapper                                      #
    # ------------------------------------------------------------------ #

    def _api_get(self, url: str, params: dict | None = None) -> list:
        """Make OKX API request, check error code, return data array."""
        resp = self._http.get(url, params)
        if resp.get("code") != "0":
            raise RuntimeError(f"OKX API error: {resp}")
        return resp["data"]

    # ------------------------------------------------------------------ #
    #  Internal: paginated fetch helpers                                   #
    # ------------------------------------------------------------------ #

    def _paginate_klines(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int = 100,
    ) -> list[list]:
        """Paginate kline-style endpoints (after param, descending order).

        OKX returns candles newest-first.  ``after=ts`` yields rows with
        timestamp < ts.  We walk backwards from *end_ms* until we reach
        *start_ms*, then sort ascending.
        """
        all_data: list[list] = []
        cursor = end_ms

        while True:
            params = {
                **params_base,
                "after": str(cursor),
                "limit": str(limit),
            }
            data = self._api_get(f"{BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            oldest_ts = int(data[-1][0])
            logger.info("Fetched %d candles (total: %d)", len(data), len(all_data))

            if oldest_ts <= start_ms or len(data) < limit:
                break
            cursor = oldest_ts

        all_data.sort(key=lambda r: int(r[0]))
        return all_data

    def _paginate_funding(
        self,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int = 100,
    ) -> list[dict]:
        """Paginate funding-rate endpoint (after param, dict records)."""
        all_data: list[dict] = []
        cursor = end_ms

        while True:
            params = {
                **params_base,
                "after": str(cursor),
                "limit": str(limit),
            }
            data = self._api_get(
                f"{BASE_URL}/api/v5/public/funding-rate-history", params,
            )
            if not data:
                break

            all_data.extend(data)
            oldest_ts = int(data[-1]["fundingTime"])
            logger.info(
                "Fetched %d funding records (total: %d)", len(data), len(all_data),
            )

            if oldest_ts <= start_ms or len(data) < limit:
                break
            cursor = oldest_ts

        all_data.sort(key=lambda r: int(r["fundingTime"]))
        return all_data

    def _paginate_rubik(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
    ) -> list[list]:
        """Paginate rubik analytics endpoints (begin/end params, array rows)."""
        all_data: list[list] = []
        current_end = end_ms

        while True:
            params = {
                **params_base,
                "begin": str(start_ms),
                "end": str(current_end),
            }
            data = self._api_get(f"{BASE_URL}{endpoint}", params)
            if not data:
                break

            all_data.extend(data)
            oldest_ts = int(data[-1][0])
            logger.info("Fetched %d records (total: %d)", len(data), len(all_data))

            if oldest_ts <= start_ms or len(data) < 100:
                break
            current_end = oldest_ts - 1

        all_data.sort(key=lambda r: int(r[0]))
        return all_data

    # ------------------------------------------------------------------ #
    #  Internal: raw → canonical DataFrame converters                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _klines_to_ohlcv_df(raw: list[list]) -> pd.DataFrame:
        """Convert OKX kline arrays to canonical OHLCV DataFrame.

        OKX kline row: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        """
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "volCcy", "quote_volume", "confirm",
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True)
        # OKX does not provide a separate close_time; use timestamp as proxy
        df["close_time"] = df["timestamp"]

        float_cols = ["open", "high", "low", "close", "volume", "quote_volume"]
        for col in float_cols:
            df[col] = df[col].astype(float)

        # Fields not available in OKX klines
        df["trades"] = 0
        df["taker_buy_volume"] = float("nan")
        df["taker_buy_quote_volume"] = float("nan")

        return df[DataType.OHLCV.columns]

    @staticmethod
    def _klines_to_price_df(raw: list[list]) -> pd.DataFrame:
        """Convert OKX kline arrays to index/mark price DataFrame."""
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close",
            "_vol", "_volCcy", "_volCcyQuote", "_confirm",
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True)
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        return df[["timestamp", "open", "high", "low", "close"]]

    # ------------------------------------------------------------------ #
    #  Fetch implementations per DataType                                  #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/api/v5/market/history-candles",
            {"instId": _to_inst_id(symbol), "bar": _convert_bar(interval)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total klines fetched: %d", symbol, len(raw))
        return self._klines_to_ohlcv_df(raw)

    def _fetch_index_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/api/v5/market/index-candles",
            {"instId": _to_index_inst_id(symbol), "bar": _convert_bar(interval)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total index price klines: %d", symbol, len(raw))
        return self._klines_to_price_df(raw)

    def _fetch_mark_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        raw = self._paginate_klines(
            "/api/v5/market/mark-price-candles",
            {"instId": _to_inst_id(symbol), "bar": _convert_bar(interval)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total mark price klines: %d", symbol, len(raw))
        return self._klines_to_price_df(raw)

    def _fetch_funding_rate(self, symbol, start_time, end_time, **_) -> pd.DataFrame:
        raw = self._paginate_funding(
            {"instId": _to_inst_id(symbol)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total funding rate records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "fundingTime": "timestamp",
            "fundingRate": "funding_rate",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True)
        df["funding_rate"] = df["funding_rate"].astype(float)
        df["symbol"] = symbol
        df["mark_price"] = float("nan")

        return df[DataType.FUNDING_RATE.columns]

    def _fetch_open_interest(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_rubik(
            "/api/v5/rubik/stat/contracts-open-interest-history",
            {"instId": _to_inst_id(symbol), "period": _convert_bar(period)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total OI history records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["ts", "oi", "oiCcy"])
        df["timestamp"] = pd.to_datetime(df["ts"].astype(int), unit="ms", utc=True)
        df["open_interest"] = df["oi"].astype(float)
        df["open_interest_value"] = df["oiCcy"].astype(float)
        df["symbol"] = symbol

        return df[DataType.OPEN_INTEREST.columns]

    def _fetch_long_short_ratio(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_rubik(
            "/api/v5/rubik/stat/contracts-long-short-account-ratio",
            {"instId": _to_inst_id(symbol), "period": _convert_bar(period)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total LS ratio records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["ts", "ratio"])
        df["timestamp"] = pd.to_datetime(df["ts"].astype(int), unit="ms", utc=True)
        df["long_short_ratio"] = df["ratio"].astype(float)
        df["long_account"] = df["long_short_ratio"] / (1 + df["long_short_ratio"])
        df["short_account"] = 1 / (1 + df["long_short_ratio"])
        df["symbol"] = symbol

        return df[DataType.LONG_SHORT_RATIO.columns]

    def _fetch_taker_buy_sell(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        raw = self._paginate_rubik(
            "/api/v5/rubik/stat/taker-volume",
            {"ccy": _to_ccy(symbol), "instType": "CONTRACTS", "period": _convert_bar(period)},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total taker buy/sell records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["ts", "sellVol", "buyVol"])
        df["timestamp"] = pd.to_datetime(df["ts"].astype(int), unit="ms", utc=True)
        df["buy_vol"] = df["buyVol"].astype(float)
        df["sell_vol"] = df["sellVol"].astype(float)
        df["buy_sell_ratio"] = df["buy_vol"] / df["sell_vol"]

        return df[DataType.TAKER_BUY_SELL.columns]
