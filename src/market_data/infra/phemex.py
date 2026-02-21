"""Phemex USDT-M Futures adapter implementing FuturesDataSource.

Maps Phemex-specific API responses to the canonical DataType schemas
defined in the domain layer.

Supported data types:
- OHLCV (via /exchange/public/md/v2/kline/list)
- FUNDING_RATE (via /api-data/public/data/funding-rate-history)
"""

import logging
import math

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://api.phemex.com"

_INTERVAL_MAP: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

_SUPPORTED_TYPES = {DataType.OHLCV, DataType.FUNDING_RATE}


class PhemexFuturesSource:
    """Phemex USDT-M Futures data source.

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
        return "phemex"

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
        if data_type not in _SUPPORTED_TYPES:
            raise ValueError(
                f"Phemex does not support {data_type.value!r}. "
                f"Supported: {', '.join(dt.value for dt in _SUPPORTED_TYPES)}"
            )
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
        )

    # ------------------------------------------------------------------ #
    #  Internal: API helper                                                #
    # ------------------------------------------------------------------ #

    def _api_get(self, url: str, params: dict) -> dict:
        """Make API call and extract data, raising on API errors."""
        resp = self._http.get(url, params)
        code = resp.get("code", -1)
        if code != 0:
            raise RuntimeError(
                f"Phemex API error {code}: {resp.get('msg', 'unknown')}"
            )
        return resp.get("data", {})

    # ------------------------------------------------------------------ #
    #  OHLCV                                                               #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(
        self, symbol: str, start_time, end_time, interval: str | None, **_,
    ) -> pd.DataFrame:
        if interval is None:
            raise ValueError("interval is required for OHLCV")

        resolution = _INTERVAL_MAP.get(interval)
        if resolution is None:
            raise ValueError(
                f"Unsupported interval {interval!r}. "
                f"Supported: {', '.join(_INTERVAL_MAP)}"
            )

        start_s = to_milliseconds(start_time) // 1000
        end_s = to_milliseconds(end_time) // 1000

        raw = self._paginate_klines(symbol, resolution, start_s, end_s)
        logger.info("[%s] Total klines fetched: %d", symbol, len(raw))
        return self._klines_to_df(raw)

    def _paginate_klines(
        self,
        symbol: str,
        resolution: int,
        start_s: int,
        end_s: int,
    ) -> list[list]:
        all_data: list[list] = []
        current = start_s

        while current < end_s:
            data = self._api_get(
                f"{BASE_URL}/exchange/public/md/v2/kline/list",
                {
                    "symbol": symbol,
                    "resolution": resolution,
                    "from": current,
                    "to": end_s,
                },
            )
            rows = data.get("rows", [])
            if not rows:
                break

            all_data.extend(rows)
            logger.info("Fetched %d candles (total: %d)", len(rows), len(all_data))

            last_ts = rows[-1][0]
            next_start = last_ts + resolution
            if next_start <= current:
                break
            current = next_start

        return all_data

    @staticmethod
    def _klines_to_df(raw: list[list]) -> pd.DataFrame:
        """Convert Phemex kline rows to canonical OHLCV DataFrame.

        Row format: [ts, interval, lastClose, open, high, low, close,
                     volume, turnover, symbol]
        """
        if not raw:
            return pd.DataFrame()

        records = []
        for row in raw:
            records.append({
                "timestamp": row[0],
                "open": float(row[3]),
                "high": float(row[4]),
                "low": float(row[5]),
                "close": float(row[6]),
                "volume": float(row[7]),
                "close_time": pd.NaT,
                "quote_volume": float(row[8]),
                "trades": 0,
                "taker_buy_volume": math.nan,
                "taker_buy_quote_volume": math.nan,
            })

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
        return df[DataType.OHLCV.columns]

    # ------------------------------------------------------------------ #
    #  Funding Rate                                                        #
    # ------------------------------------------------------------------ #

    def _fetch_funding_rate(
        self, symbol: str, start_time, end_time, **_,
    ) -> pd.DataFrame:
        start_ms = to_milliseconds(start_time)
        end_ms = to_milliseconds(end_time)
        fr_symbol = f".{symbol}FR8H"

        raw = self._paginate_funding_rate(fr_symbol, start_ms, end_ms)
        logger.info("[%s] Total funding rate records: %d", symbol, len(raw))

        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)
        df = df.rename(columns={
            "fundingTime": "timestamp",
            "fundingRate": "funding_rate",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["funding_rate"] = df["funding_rate"].astype(float)
        df["symbol"] = symbol
        df["mark_price"] = math.nan
        return df[DataType.FUNDING_RATE.columns]

    def _paginate_funding_rate(
        self,
        fr_symbol: str,
        start_ms: int,
        end_ms: int,
        limit: int = 100,
    ) -> list[dict]:
        all_data: list[dict] = []
        current = start_ms

        while current < end_ms:
            data = self._api_get(
                f"{BASE_URL}/api-data/public/data/funding-rate-history",
                {
                    "symbol": fr_symbol,
                    "start": current,
                    "end": end_ms,
                    "limit": limit,
                },
            )
            rows = data.get("rows", [])
            if not rows:
                break

            all_data.extend(rows)
            logger.info(
                "Fetched %d funding records (total: %d)",
                len(rows), len(all_data),
            )

            if len(rows) < limit:
                break
            current = rows[-1]["fundingTime"] + 1

        return all_data
