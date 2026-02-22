"""Bybit USDT Perpetual Futures adapter implementing FuturesDataSource.

Maps Bybit V5 API responses to the canonical DataType schemas
defined in the domain layer.
"""

import logging

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://api.bybit.com"

# Canonical interval → Bybit kline interval
_INTERVAL_MAP = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W", "1M": "M",
}

# Canonical period → Bybit intervalTime / period
_PERIOD_MAP = {
    "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "4h": "4h", "1d": "1d",
}


class BybitFuturesSource:
    """Bybit USDT Perpetual Futures data source.

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
        return "bybit"

    def close(self):
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # ------------------------------------------------------------------ #
    #  Internal: Bybit API response wrapper                                #
    # ------------------------------------------------------------------ #

    def _api_get(self, url, params=None):
        """Call Bybit API, validate retCode, and return result payload."""
        resp = self._http.get(url, params)
        if resp.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error: {resp}")
        return resp["result"]

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
        }
        handler = dispatcher.get(data_type)
        if handler is None:
            raise NotImplementedError(
                f"Bybit adapter does not support {data_type.value}"
            )
        return handler(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            period=period,
        )

    # ------------------------------------------------------------------ #
    #  Internal: paginated fetch helpers                                   #
    # ------------------------------------------------------------------ #

    def _paginate_klines(
        self,
        endpoint: str,
        params_base: dict,
        start_ms: int,
        end_ms: int,
        limit: int = 200,
    ) -> list[list]:
        """Paginate Bybit kline endpoints (results arrive in descending order)."""
        all_data: list[list] = []
        current_end = end_ms

        while current_end > start_ms:
            params = {
                **params_base,
                "start": start_ms,
                "end": current_end,
                "limit": limit,
            }
            result = self._api_get(f"{BASE_URL}{endpoint}", params)
            items = result.get("list", [])
            if not items:
                break

            all_data.extend(items)
            logger.info("Fetched %d candles (total: %d)", len(items), len(all_data))

            if len(items) < limit:
                break

            # Descending order: last item is oldest
            oldest_ts = int(items[-1][0])
            current_end = oldest_ts - 1

        # Sort ascending by timestamp
        all_data.sort(key=lambda x: int(x[0]))
        return all_data

    def _paginate_funding(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 200,
    ) -> list[dict]:
        """Paginate Bybit funding rate history (descending order)."""
        all_data: list[dict] = []
        current_end = end_ms

        while current_end > start_ms:
            params = {
                "category": "linear",
                "symbol": symbol,
                "startTime": start_ms,
                "endTime": current_end,
                "limit": limit,
            }
            result = self._api_get(f"{BASE_URL}/v5/market/funding/history", params)
            items = result.get("list", [])
            if not items:
                break

            all_data.extend(items)
            logger.info("Fetched %d funding records (total: %d)", len(items), len(all_data))

            if len(items) < limit:
                break

            oldest_ts = int(items[-1]["fundingRateTimestamp"])
            current_end = oldest_ts - 1

        all_data.sort(key=lambda x: int(x["fundingRateTimestamp"]))
        return all_data

    def _paginate_open_interest(
        self,
        symbol: str,
        start_ms: int,
        end_ms: int,
        interval_time: str,
        limit: int = 200,
    ) -> list[dict]:
        """Paginate Bybit open interest (cursor-based)."""
        all_data: list[dict] = []
        cursor = ""

        while True:
            params = {
                "category": "linear",
                "symbol": symbol,
                "intervalTime": interval_time,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": limit,
            }
            if cursor:
                params["cursor"] = cursor

            result = self._api_get(f"{BASE_URL}/v5/market/open-interest", params)
            items = result.get("list", [])
            if not items:
                break

            all_data.extend(items)
            logger.info("Fetched %d OI records (total: %d)", len(items), len(all_data))

            cursor = result.get("nextPageCursor", "")
            if not cursor or len(items) < limit:
                break

        return all_data

    # ------------------------------------------------------------------ #
    #  Internal: raw → canonical DataFrame converters                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _klines_to_ohlcv_df(raw: list[list]) -> pd.DataFrame:
        """Convert Bybit kline rows to OHLCV canonical DataFrame."""
        if not raw:
            return pd.DataFrame()

        rows = []
        for item in raw:
            rows.append({
                "timestamp": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
                "close_time": None,
                "quote_volume": float(item[6]),  # turnover
                "trades": 0,
                "taker_buy_volume": float("nan"),
                "taker_buy_quote_volume": float("nan"),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df[DataType.OHLCV.columns]

    @staticmethod
    def _klines_to_price_df(raw: list[list]) -> pd.DataFrame:
        """Convert Bybit kline rows to price-only (INDEX/MARK) DataFrame."""
        if not raw:
            return pd.DataFrame()

        rows = []
        for item in raw:
            rows.append({
                "timestamp": int(item[0]),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df[DataType.INDEX_PRICE.columns]

    # ------------------------------------------------------------------ #
    #  Fetch implementations per DataType                                  #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        bybit_interval = _INTERVAL_MAP.get(interval, interval)
        raw = self._paginate_klines(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": bybit_interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total klines fetched: %d", symbol, len(raw))
        return self._klines_to_ohlcv_df(raw)

    def _fetch_index_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        bybit_interval = _INTERVAL_MAP.get(interval, interval)
        raw = self._paginate_klines(
            "/v5/market/index-price-kline",
            {"category": "linear", "symbol": symbol, "interval": bybit_interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total index price klines: %d", symbol, len(raw))
        return self._klines_to_price_df(raw)

    def _fetch_mark_price(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        bybit_interval = _INTERVAL_MAP.get(interval, interval)
        raw = self._paginate_klines(
            "/v5/market/mark-price-kline",
            {"category": "linear", "symbol": symbol, "interval": bybit_interval},
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total mark price klines: %d", symbol, len(raw))
        return self._klines_to_price_df(raw)

    def _fetch_funding_rate(self, symbol, start_time, end_time, **_) -> pd.DataFrame:
        raw = self._paginate_funding(
            symbol,
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total funding rate records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        rows = []
        for item in raw:
            rows.append({
                "timestamp": int(item["fundingRateTimestamp"]),
                "symbol": item["symbol"],
                "funding_rate": float(item["fundingRate"]),
                "mark_price": float("nan"),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df[DataType.FUNDING_RATE.columns]

    def _fetch_open_interest(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        bybit_period = _PERIOD_MAP.get(period, period)
        raw = self._paginate_open_interest(
            symbol,
            to_milliseconds(start_time),
            to_milliseconds(end_time),
            bybit_period,
        )
        logger.info("[%s] Total OI records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        rows = []
        for item in raw:
            rows.append({
                "timestamp": int(item["timestamp"]),
                "symbol": symbol,
                "open_interest": float(item["openInterest"]),
                "open_interest_value": float("nan"),
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df[DataType.OPEN_INTEREST.columns]

    def _fetch_long_short_ratio(self, symbol, start_time, end_time, period, **_) -> pd.DataFrame:
        bybit_period = _PERIOD_MAP.get(period, period)
        params = {
            "category": "linear",
            "symbol": symbol,
            "period": bybit_period,
            "limit": 500,
        }
        result = self._api_get(f"{BASE_URL}/v5/market/account-ratio", params)
        items = result.get("list", [])

        if not items:
            return pd.DataFrame()

        rows = []
        for item in items:
            buy_ratio = float(item["buyRatio"])
            sell_ratio = float(item["sellRatio"])
            rows.append({
                "timestamp": int(item["timestamp"]),
                "symbol": item["symbol"],
                "long_short_ratio": buy_ratio / sell_ratio if sell_ratio != 0 else float("nan"),
                "long_account": buy_ratio,
                "short_account": sell_ratio,
            })

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df[DataType.LONG_SHORT_RATIO.columns]
