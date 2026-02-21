"""Kraken data source adapter implementing FuturesDataSource.

Maps Kraken Spot and Futures API responses to the canonical DataType schemas
defined in the domain layer.

Supported DataTypes:
- OHLCV: via Kraken Spot API (most reliable)
- FUNDING_RATE: via Kraken Futures API
"""

import logging

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

SPOT_BASE_URL = "https://api.kraken.com/0/public"
FUTURES_BASE_URL = "https://futures.kraken.com/derivatives/api/v3"

_INTERVAL_MAP: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080,
}


class KrakenFuturesSource:
    """Kraken data source (Spot + Futures APIs).

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
        return "kraken"

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
            DataType.FUNDING_RATE: self._fetch_funding_rate,
        }
        handler = dispatcher[data_type]
        return handler(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
            period=period,
        )

    # ------------------------------------------------------------------ #
    #  Internal: API helpers                                                #
    # ------------------------------------------------------------------ #

    def _api_get_spot(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to the Kraken Spot API.

        Raises RuntimeError if the API returns errors.
        """
        data = self._http.get(f"{SPOT_BASE_URL}{endpoint}", params)
        if data.get("error"):
            raise RuntimeError(f"Kraken API error: {data['error']}")
        return data["result"]

    def _api_get_futures(self, endpoint: str, params: dict | None = None) -> dict:
        """Make a request to the Kraken Futures API.

        Raises RuntimeError if the result is not 'success'.
        """
        data = self._http.get(f"{FUTURES_BASE_URL}{endpoint}", params)
        if data.get("result") != "success":
            raise RuntimeError(f"Kraken Futures API error: {data}")
        return data

    # ------------------------------------------------------------------ #
    #  Fetch: OHLCV (Spot API)                                             #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        kraken_interval = _INTERVAL_MAP.get(interval)
        if kraken_interval is None:
            raise ValueError(
                f"Unsupported interval: {interval!r}. "
                f"Supported: {', '.join(sorted(_INTERVAL_MAP))}"
            )

        start_s = to_milliseconds(start_time) // 1000
        end_s = to_milliseconds(end_time) // 1000

        all_rows: list[list] = []
        current_since = start_s

        while current_since < end_s:
            result = self._api_get_spot("/OHLC", {
                "pair": symbol,
                "interval": kraken_interval,
                "since": current_since,
            })

            # result keys: pair name (varies, e.g. "XXBTZUSD") + "last"
            last = result.get("last", 0)
            pair_keys = [k for k in result if k != "last"]
            if not pair_keys:
                break

            rows = result[pair_keys[0]]
            if not rows:
                break

            # Filter rows within our time range
            rows = [r for r in rows if r[0] < end_s]
            all_rows.extend(rows)

            logger.info("Fetched %d candles (total: %d)", len(rows), len(all_rows))

            if last <= current_since:
                break
            current_since = last

        return self._ohlcv_to_df(all_rows)

    @staticmethod
    def _ohlcv_to_df(raw: list[list]) -> pd.DataFrame:
        """Convert Kraken OHLC rows to canonical DataFrame.

        Kraken format: [timestamp, open, high, low, close, vwap, volume, count]
        """
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=[
            "timestamp", "open", "high", "low", "close",
            "vwap", "volume", "count",
        ])

        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

        float_cols = ["open", "high", "low", "close", "volume"]
        for col in float_cols:
            df[col] = df[col].astype(float)
        df["trades"] = df["count"].astype(int)

        # Columns not available in Kraken Spot API → NaN
        df["close_time"] = float("nan")
        df["quote_volume"] = float("nan")
        df["taker_buy_volume"] = float("nan")
        df["taker_buy_quote_volume"] = float("nan")

        return df[DataType.OHLCV.columns]

    # ------------------------------------------------------------------ #
    #  Fetch: FUNDING_RATE (Futures API)                                   #
    # ------------------------------------------------------------------ #

    def _fetch_funding_rate(self, symbol, start_time, end_time, **_) -> pd.DataFrame:
        data = self._api_get_futures("/historicalfundingrates", {
            "symbol": symbol,
        })

        rates = data.get("rates", [])
        if not rates:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

        # Filter by time range
        start_dt = pd.to_datetime(to_milliseconds(start_time), unit="ms", utc=True)
        end_dt = pd.to_datetime(to_milliseconds(end_time), unit="ms", utc=True)
        df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] < end_dt)]

        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"fundingRate": "funding_rate"})
        df["funding_rate"] = df["funding_rate"].astype(float)
        df["symbol"] = symbol
        df["mark_price"] = float("nan")

        return df[DataType.FUNDING_RATE.columns].reset_index(drop=True)
