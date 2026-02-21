"""market_data: exchange-agnostic futures market data retrieval.

Usage:
    from market_data import create_source, DataType

    source = create_source("binance")
    df = source.fetch(DataType.OHLCV, "BTCUSDT", "2025-01-01", "2025-02-01", interval="1h")
"""

from .domain.models import DataType
from .domain.source import FuturesDataSource

_REGISTRY: dict[str, type] = {}


def _ensure_registry() -> None:
    """Lazily populate the registry on first use."""
    if _REGISTRY:
        return
    from .infra.binance import BinanceFuturesSource
    from .infra.kraken import KrakenFuturesSource

    _REGISTRY["binance"] = BinanceFuturesSource
    _REGISTRY["kraken"] = KrakenFuturesSource


def create_source(exchange: str, **kwargs) -> FuturesDataSource:
    """Create a FuturesDataSource for the given exchange.

    Args:
        exchange: Exchange name ('binance', and in the future 'bybit', 'okx', ...).
        **kwargs: Passed to the exchange adapter constructor.

    Raises:
        ValueError: If the exchange is not supported.
    """
    _ensure_registry()
    cls = _REGISTRY.get(exchange.lower())
    if cls is None:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unsupported exchange: {exchange!r}. Supported: {supported}"
        )
    return cls(**kwargs)


__all__ = ["DataType", "FuturesDataSource", "create_source"]
