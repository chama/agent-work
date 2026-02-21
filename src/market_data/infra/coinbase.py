"""Coinbase Exchange (Spot) adapter implementing FuturesDataSource.

Maps Coinbase-specific API responses to the canonical DataType schemas
defined in the domain layer. Only OHLCV is supported (Coinbase is primarily
a spot exchange).
"""

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://api.exchange.coinbase.com"

_INTERVAL_TO_GRANULARITY: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "1d": 86400,
}

_MAX_CANDLES = 300


def _to_product_id(symbol: str) -> str:
    """Convert a compact symbol like 'BTCUSDT' or 'BTCUSD' to Coinbase format.

    Examples:
        'BTCUSDT' -> 'BTC-USDT'
        'BTCUSD'  -> 'BTC-USD'
        'ETHUSDT' -> 'ETH-USDT'
        'BTC-USD' -> 'BTC-USD'  (already in Coinbase format)
    """
    if "-" in symbol:
        return symbol.upper()

    sym = symbol.upper()
    for quote in ("USDT", "USD"):
        if sym.endswith(quote):
            base = sym[: -len(quote)]
            return f"{base}-{quote}"

    raise ValueError(
        f"Cannot convert symbol {symbol!r} to Coinbase product ID. "
        "Expected format like 'BTCUSDT', 'BTCUSD', or 'BTC-USD'."
    )


class CoinbaseSource:
    """Coinbase Exchange (Spot) data source.

    Implements the ``FuturesDataSource`` protocol.
    Only ``DataType.OHLCV`` is supported.
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
        return "coinbase"

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
    #  Internal: paginated fetch                                           #
    # ------------------------------------------------------------------ #

    def _paginate_candles(
        self,
        product_id: str,
        granularity: int,
        start_ms: int,
        end_ms: int,
    ) -> list[list]:
        """Fetch candles with pagination by shifting the time window."""
        all_data: list[list] = []
        current_start_s = start_ms // 1000

        end_s = end_ms // 1000

        while current_start_s < end_s:
            chunk_end_s = min(
                current_start_s + granularity * _MAX_CANDLES,
                end_s,
            )

            start_iso = datetime.fromtimestamp(
                current_start_s, tz=timezone.utc
            ).isoformat()
            end_iso = datetime.fromtimestamp(
                chunk_end_s, tz=timezone.utc
            ).isoformat()

            params = {
                "start": start_iso,
                "end": end_iso,
                "granularity": granularity,
            }
            data = self._http.get(
                f"{BASE_URL}/products/{product_id}/candles", params
            )
            if not data:
                break

            all_data.extend(data)
            logger.info(
                "Fetched %d candles (total: %d)", len(data), len(all_data)
            )

            current_start_s = chunk_end_s

        return all_data

    # ------------------------------------------------------------------ #
    #  Internal: raw → canonical DataFrame converter                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _candles_to_df(raw: list[list]) -> pd.DataFrame:
        """Convert Coinbase candle data to canonical OHLCV DataFrame.

        Coinbase returns: [time, low, high, open, close, volume]
        Canonical order:  timestamp, open, high, low, close, volume, ...
        """
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw, columns=["time", "low", "high", "open", "close", "volume"])

        # Sort ascending by time (Coinbase returns descending)
        df = df.sort_values("time").reset_index(drop=True)

        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)

        # Coinbase doesn't provide these fields → fill with NaN / 0
        df["close_time"] = pd.NaT
        df["quote_volume"] = np.nan
        df["trades"] = 0
        df["taker_buy_volume"] = np.nan
        df["taker_buy_quote_volume"] = np.nan

        return df[DataType.OHLCV.columns]

    # ------------------------------------------------------------------ #
    #  Fetch implementation                                                #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        if interval not in _INTERVAL_TO_GRANULARITY:
            supported = ", ".join(sorted(_INTERVAL_TO_GRANULARITY))
            raise ValueError(
                f"Unsupported interval {interval!r} for Coinbase. "
                f"Supported: {supported}"
            )

        product_id = _to_product_id(symbol)
        granularity = _INTERVAL_TO_GRANULARITY[interval]

        raw = self._paginate_candles(
            product_id,
            granularity,
            to_milliseconds(start_time),
            to_milliseconds(end_time),
        )
        logger.info("[%s] Total candles fetched: %d", product_id, len(raw))
        return self._candles_to_df(raw)
