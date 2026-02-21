"""Tests for scripts/export_binance_data.py."""

import re
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Import from scripts — adjust sys.path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_binance_data import (
    ALL_TYPES,
    ANALYTICS_TYPES,
    KLINE_TYPES,
    fetch_and_save,
    make_filename,
    parse_args,
    main,
)


# ------------------------------------------------------------------ #
#  make_filename                                                       #
# ------------------------------------------------------------------ #


class TestMakeFilename:
    def test_with_interval(self):
        with patch("export_binance_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 21, 14, 30, 0)
            result = make_filename("BTCUSDT", "klines", "1h")
        assert result == "20260221_1430_btcusdt_1h_klines.csv"

    def test_without_interval(self):
        with patch("export_binance_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 21, 9, 5, 0)
            result = make_filename("ETHUSDT", "funding_rate", None)
        assert result == "20260221_0905_ethusdt_funding_rate.csv"

    def test_filename_matches_pattern(self):
        result = make_filename("BTCUSDT", "klines", "4h")
        pattern = r"^\d{8}_\d{4}_btcusdt_4h_klines\.csv$"
        assert re.match(pattern, result)


# ------------------------------------------------------------------ #
#  parse_args                                                          #
# ------------------------------------------------------------------ #


class TestParseArgs:
    def test_required_args(self):
        args = parse_args(["--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01"])
        assert args.symbol == "BTCUSDT"
        assert args.start == "2025-01-01"
        assert args.end == "2025-02-01"
        assert args.interval == "1h"
        assert args.period == "1h"
        assert args.types is None

    def test_custom_types(self):
        args = parse_args([
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
            "--types", "klines,funding_rate",
        ])
        assert args.types == "klines,funding_rate"

    def test_custom_interval_and_period(self):
        args = parse_args([
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
            "--interval", "4h", "--period", "15m",
        ])
        assert args.interval == "4h"
        assert args.period == "15m"

    def test_list_types_flag(self):
        args = parse_args(["--list-types"])
        assert args.list_types is True


# ------------------------------------------------------------------ #
#  fetch_and_save                                                      #
# ------------------------------------------------------------------ #


class TestFetchAndSave:
    def test_klines_saves_csv(self, tmp_path):
        mock_client = MagicMock()
        mock_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "open": [50000.0, 51000.0],
            "high": [51000.0, 52000.0],
            "low": [49000.0, 50000.0],
            "close": [50500.0, 51500.0],
            "volume": [100.0, 200.0],
        })
        mock_client.get_klines.return_value = mock_df

        result = fetch_and_save(
            mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", "klines", tmp_path,
        )

        assert result is not None
        assert result.exists()
        assert result.suffix == ".csv"
        assert "btcusdt" in result.name
        assert "klines" in result.name
        mock_client.get_klines.assert_called_once_with("BTCUSDT", "1h", "2025-01-01", "2025-01-02")

    def test_funding_rate_saves_csv(self, tmp_path):
        mock_client = MagicMock()
        mock_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01"]),
            "funding_rate": [0.0001],
        })
        mock_client.get_funding_rate_history.return_value = mock_df

        result = fetch_and_save(
            mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", "funding_rate", tmp_path,
        )

        assert result is not None
        assert "funding_rate" in result.name
        # funding_rate has no interval in filename
        assert "_1h_funding_rate" not in result.name

    def test_empty_df_returns_none(self, tmp_path):
        mock_client = MagicMock()
        mock_client.get_klines.return_value = pd.DataFrame()

        result = fetch_and_save(
            mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", "klines", tmp_path,
        )

        assert result is None

    def test_unknown_type_returns_none(self, tmp_path):
        mock_client = MagicMock()

        result = fetch_and_save(
            mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", "unknown_type", tmp_path,
        )

        assert result is None

    def test_all_kline_types_use_interval(self, tmp_path):
        for dtype in KLINE_TYPES:
            mock_client = MagicMock()
            mock_df = pd.DataFrame({"col": [1]})
            # Set up all kline methods to return the mock df
            mock_client.get_klines.return_value = mock_df
            mock_client.get_index_price_klines.return_value = mock_df
            mock_client.get_mark_price_klines.return_value = mock_df

            result = fetch_and_save(
                mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
                "4h", "1h", dtype, tmp_path,
            )

            assert result is not None
            assert "4h" in result.name, f"{dtype} should include interval in filename"

    def test_all_analytics_types_exist(self):
        """Ensure all analytics types are mapped in fetchers."""
        mock_client = MagicMock()
        # All fetch methods return empty DataFrame
        for attr in dir(mock_client):
            if attr.startswith("get_"):
                getattr(mock_client, attr).return_value = pd.DataFrame()

        for dtype in ANALYTICS_TYPES:
            # Should not raise "Unknown data type"
            result = fetch_and_save(
                mock_client, "BTCUSDT", "2025-01-01", "2025-01-02",
                "1h", "1h", dtype, Path("/tmp"),
            )
            # Empty DF -> returns None, but no error
            assert result is None


# ------------------------------------------------------------------ #
#  main (integration-like tests)                                       #
# ------------------------------------------------------------------ #


class TestMain:
    def test_list_types_returns_zero(self, capsys):
        ret = main(["--list-types"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "klines" in captured.out

    def test_missing_required_args_returns_one(self):
        ret = main(["--symbol", "BTCUSDT"])
        assert ret == 1

    def test_invalid_type_returns_one(self):
        ret = main([
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
            "--types", "invalid_type",
        ])
        assert ret == 1

    def test_successful_run(self, tmp_path):
        mock_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01"]),
            "open": [50000.0],
        })

        with patch("export_binance_data.BinanceFuturesClient") as MockClient:
            instance = MockClient.return_value
            instance.get_klines.return_value = mock_df

            ret = main([
                "--symbol", "BTCUSDT",
                "--start", "2025-01-01",
                "--end", "2025-02-01",
                "--types", "klines",
                "--output-dir", str(tmp_path),
            ])

        assert ret == 0
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1
        assert "klines" in csv_files[0].name
