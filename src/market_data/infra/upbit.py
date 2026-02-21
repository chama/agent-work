"""Upbit Spot adapter implementing FuturesDataSource protocol.

Upbit is a spot-only exchange (no futures), so only OHLCV data is supported.
Maps Upbit-specific API responses to the canonical DataType schemas
defined in the domain layer.
"""

import logging
import math
import re

import pandas as pd

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upbit.com/v1"

# interval string → Upbit candle endpoint path
_INTERVAL_ENDPOINTS: dict[str, str] = {
    "1m": "/candles/minutes/1",
    "3m": "/candles/minutes/3",
    "5m": "/candles/minutes/5",
    "15m": "/candles/minutes/15",
    "30m": "/candles/minutes/30",
    "1h": "/candles/minutes/60",
    "4h": "/candles/minutes/240",
    "1d": "/candles/days",
    "1w": "/candles/weeks",
    "1M": "/candles/months",
}

# Pattern: BASEQUOTE (e.g. BTCUSDT, ETHKRW)
_SYMBOL_PATTERN = re.compile(
    r"^([A-Z0-9]+)(KRW|USDT|BTC|ETH)$"
)


def _to_upbit_market(symbol: str) -> str:
    """Convert Binance-style symbol to Upbit market format.

    Examples:
        'BTCUSDT' → 'USDT-BTC'
        'BTCKRW'  → 'KRW-BTC'
        'ETHBTC'  → 'BTC-ETH'
        'KRW-BTC' → 'KRW-BTC' (already Upbit format, pass through)
    """
    if "-" in symbol:
        return symbol

    m = _SYMBOL_PATTERN.match(symbol.upper())
    if not m:
        raise ValueError(
            f"Cannot parse symbol {symbol!r}. "
            "Use Binance format (e.g. 'BTCUSDT') or Upbit format (e.g. 'KRW-BTC')."
        )
    base, quote = m.group(1), m.group(2)
    return f"{quote}-{base}"


class UpbitSource:
    """Upbit spot data source.

    Implements the ``FuturesDataSource`` protocol.
    Only ``DataType.OHLCV`` is supported since Upbit has no futures market.
    """

    def __init__(
        self,
        max_retries: int = 3,
        rate_limit_sleep: float = 0.15,
    ):
        self._http = HttpClient(
            max_retries=max_retries,
            rate_limit_sleep=rate_limit_sleep,
        )

    @property
    def exchange(self) -> str:
        return "upbit"

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
        handler = dispatcher.get(data_type)
        if handler is None:
            raise KeyError(
                f"Upbit does not support {data_type.name}. "
                "Only OHLCV is available (spot exchange)."
            )
        return handler(
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            interval=interval,
        )

    # ------------------------------------------------------------------ #
    #  Internal: paginated candle fetch                                    #
    # ------------------------------------------------------------------ #

    def _paginate_candles(
        self,
        endpoint: str,
        market: str,
        start_ms: int,
        end_ms: int,
        count: int = 200,
    ) -> list[dict]:
        """Fetch candles by walking backwards from end_ms using the 'to' param."""
        all_data: list[dict] = []
        current_to_ms = end_ms

        while True:
            to_str = (
                pd.Timestamp(current_to_ms, unit="ms", tz="UTC")
                .strftime("%Y-%m-%dT%H:%M:%S")
            )
            params = {
                "market": market,
                "to": to_str,
                "count": count,
            }
            data = self._http.get(f"{BASE_URL}{endpoint}", params)
            if not data:
                break

            # Filter out candles before start_ms
            filtered = [
                c for c in data
                if c["timestamp"] >= start_ms
            ]
            all_data.extend(filtered)

            logger.info(
                "Fetched %d candles (total: %d)", len(filtered), len(all_data),
            )

            # If we received fewer than requested, we've reached the end
            if len(data) < count:
                break

            # The oldest candle in this batch — use its time as the next 'to'
            oldest = min(data, key=lambda c: c["timestamp"])
            oldest_ms = oldest["timestamp"]

            # Stop if we've reached or passed start_ms
            if oldest_ms <= start_ms:
                break

            current_to_ms = oldest_ms

        return all_data

    # ------------------------------------------------------------------ #
    #  Internal: raw → canonical DataFrame converter                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _candles_to_df(raw: list[dict]) -> pd.DataFrame:
        """Convert Upbit candle records to canonical OHLCV DataFrame."""
        if not raw:
            return pd.DataFrame()

        df = pd.DataFrame(raw)

        result = pd.DataFrame()
        result["timestamp"] = pd.to_datetime(
            df["candle_date_time_utc"], utc=True,
        )
        result["open"] = df["opening_price"].astype(float)
        result["high"] = df["high_price"].astype(float)
        result["low"] = df["low_price"].astype(float)
        result["close"] = df["trade_price"].astype(float)
        result["volume"] = df["candle_acc_trade_volume"].astype(float)
        result["close_time"] = float("nan")
        result["quote_volume"] = df["candle_acc_trade_price"].astype(float)
        result["trades"] = 0
        result["taker_buy_volume"] = float("nan")
        result["taker_buy_quote_volume"] = float("nan")

        result = result.sort_values("timestamp").reset_index(drop=True)
        return result

    # ------------------------------------------------------------------ #
    #  Fetch implementation                                                #
    # ------------------------------------------------------------------ #

    def _fetch_ohlcv(self, symbol, start_time, end_time, interval, **_) -> pd.DataFrame:
        if interval is None:
            raise ValueError("interval is required for OHLCV data")

        endpoint = _INTERVAL_ENDPOINTS.get(interval)
        if endpoint is None:
            supported = ", ".join(sorted(_INTERVAL_ENDPOINTS))
            raise ValueError(
                f"Unsupported interval {interval!r}. Supported: {supported}"
            )

        market = _to_upbit_market(symbol)
        start_ms = to_milliseconds(start_time)
        end_ms = to_milliseconds(end_time)

        raw = self._paginate_candles(endpoint, market, start_ms, end_ms)
        logger.info("[%s] Total candles fetched: %d", market, len(raw))
        return self._candles_to_df(raw)
