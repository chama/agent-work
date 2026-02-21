"""Standard data type definitions for cross-exchange market data.

Each DataType member defines a canonical column schema that all exchange
adapters must conform to. This guarantees that exported CSV/parquet files
have the same structure regardless of the data source.
"""

from enum import Enum


class DataType(Enum):
    """Market data types with standardised column schemas.

    Attributes:
        columns: Ordered list of column names for the canonical DataFrame.
    """

    OHLCV = "ohlcv"
    INDEX_PRICE = "index_price"
    MARK_PRICE = "mark_price"
    FUNDING_RATE = "funding_rate"
    OPEN_INTEREST = "open_interest"
    LONG_SHORT_RATIO = "long_short_ratio"
    TOP_LS_ACCOUNTS = "top_ls_accounts"
    TOP_LS_POSITIONS = "top_ls_positions"
    TAKER_BUY_SELL = "taker_buy_sell"

    @property
    def columns(self) -> list[str]:
        return _SCHEMAS[self]

    @property
    def uses_interval(self) -> bool:
        """True if this data type is parameterised by kline interval."""
        return self in _INTERVAL_TYPES

    @property
    def uses_period(self) -> bool:
        """True if this data type is parameterised by analytics period."""
        return self in _PERIOD_TYPES


_SCHEMAS: dict["DataType", list[str]] = {
    DataType.OHLCV: [
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_volume", "taker_buy_quote_volume",
    ],
    DataType.INDEX_PRICE: [
        "timestamp", "open", "high", "low", "close",
    ],
    DataType.MARK_PRICE: [
        "timestamp", "open", "high", "low", "close",
    ],
    DataType.FUNDING_RATE: [
        "timestamp", "symbol", "funding_rate", "mark_price",
    ],
    DataType.OPEN_INTEREST: [
        "timestamp", "symbol", "open_interest", "open_interest_value",
    ],
    DataType.LONG_SHORT_RATIO: [
        "timestamp", "symbol", "long_short_ratio", "long_account", "short_account",
    ],
    DataType.TOP_LS_ACCOUNTS: [
        "timestamp", "symbol", "long_short_ratio", "long_account", "short_account",
    ],
    DataType.TOP_LS_POSITIONS: [
        "timestamp", "symbol", "long_short_ratio", "long_account", "short_account",
    ],
    DataType.TAKER_BUY_SELL: [
        "timestamp", "buy_sell_ratio", "buy_vol", "sell_vol",
    ],
}

_INTERVAL_TYPES = {DataType.OHLCV, DataType.INDEX_PRICE, DataType.MARK_PRICE}
_PERIOD_TYPES = {
    DataType.OPEN_INTEREST,
    DataType.LONG_SHORT_RATIO,
    DataType.TOP_LS_ACCOUNTS,
    DataType.TOP_LS_POSITIONS,
    DataType.TAKER_BUY_SELL,
}
