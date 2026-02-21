"""Tests for market_data.domain.models."""

from market_data.domain.models import DataType


class TestDataType:
    def test_all_types_have_columns(self):
        for dt in DataType:
            assert isinstance(dt.columns, list)
            assert len(dt.columns) > 0
            assert "timestamp" in dt.columns

    def test_ohlcv_columns(self):
        cols = DataType.OHLCV.columns
        assert cols[:6] == [
            "timestamp", "open", "high", "low", "close", "volume",
        ]

    def test_funding_rate_columns(self):
        cols = DataType.FUNDING_RATE.columns
        assert cols == ["timestamp", "symbol", "funding_rate", "mark_price"]

    def test_uses_interval(self):
        assert DataType.OHLCV.uses_interval is True
        assert DataType.INDEX_PRICE.uses_interval is True
        assert DataType.MARK_PRICE.uses_interval is True
        assert DataType.FUNDING_RATE.uses_interval is False
        assert DataType.OPEN_INTEREST.uses_interval is False

    def test_uses_period(self):
        assert DataType.OHLCV.uses_period is False
        assert DataType.OPEN_INTEREST.uses_period is True
        assert DataType.LONG_SHORT_RATIO.uses_period is True
        assert DataType.TAKER_BUY_SELL.uses_period is True

    def test_value_matches_string(self):
        assert DataType.OHLCV.value == "ohlcv"
        assert DataType.FUNDING_RATE.value == "funding_rate"

    def test_ls_types_share_columns(self):
        """Long/short ratio types should have identical schemas."""
        assert DataType.LONG_SHORT_RATIO.columns == DataType.TOP_LS_ACCOUNTS.columns
        assert DataType.LONG_SHORT_RATIO.columns == DataType.TOP_LS_POSITIONS.columns
