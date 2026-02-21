"""Exchange data source protocol (interface).

All exchange adapters (Binance, Bybit, OKX, ...) must implement this
protocol so that the application layer can work with any exchange
without knowing its specifics.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from .models import DataType


class FuturesDataSource(Protocol):
    """Unified interface for fetching futures market data.

    Each method returns a ``pd.DataFrame`` whose columns conform to the
    corresponding ``DataType.columns`` schema.
    """

    @property
    def exchange(self) -> str:
        """Short lowercase exchange name, e.g. 'binance', 'bybit'."""
        ...

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
        """Fetch market data for a given type and symbol.

        Args:
            data_type: The kind of data to retrieve.
            symbol: Trading pair (e.g. 'BTCUSDT').
            start_time: Start time ('YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS', or ms).
            end_time: End time.
            interval: Kline interval (required when ``data_type.uses_interval``).
            period: Analytics period (required when ``data_type.uses_period``).

        Returns:
            DataFrame with columns matching ``data_type.columns``.
        """
        ...
