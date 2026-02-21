"""Tests for scripts/export_data.py."""

import re
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_data import (
    ALL_TYPE_VALUES,
    INTERVAL_TYPES,
    PERIOD_TYPES,
    fetch_and_save,
    make_filename,
    parse_args,
    main,
)
from market_data import DataType


# ------------------------------------------------------------------ #
#  make_filename                                                       #
# ------------------------------------------------------------------ #


class TestMakeFilename:
    def test_with_interval(self):
        with patch("export_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 21, 14, 30, 0)
            result = make_filename("binance", "BTCUSDT", DataType.OHLCV, "1h")
        assert result == "20260221_1430_binance_btcusdt_1h_ohlcv.csv"

    def test_without_interval(self):
        with patch("export_data.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 21, 9, 5, 0)
            result = make_filename("binance", "ETHUSDT", DataType.FUNDING_RATE, None)
        assert result == "20260221_0905_binance_ethusdt_funding_rate.csv"

    def test_filename_matches_pattern(self):
        result = make_filename("binance", "BTCUSDT", DataType.OHLCV, "4h")
        pattern = r"^\d{8}_\d{4}_binance_btcusdt_4h_ohlcv\.csv$"
        assert re.match(pattern, result)

    def test_includes_exchange_name(self):
        result = make_filename("bybit", "BTCUSDT", DataType.OHLCV, "1h")
        assert "bybit" in result


# ------------------------------------------------------------------ #
#  parse_args                                                          #
# ------------------------------------------------------------------ #


class TestParseArgs:
    def test_required_args(self):
        args = parse_args([
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
        ])
        assert args.symbol == "BTCUSDT"
        assert args.start == "2025-01-01"
        assert args.end == "2025-02-01"
        assert args.exchange == "binance"
        assert args.interval == "1h"
        assert args.period == "1h"

    def test_custom_exchange(self):
        args = parse_args([
            "--exchange", "bybit",
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
        ])
        assert args.exchange == "bybit"

    def test_custom_types(self):
        args = parse_args([
            "--symbol", "BTCUSDT", "--start", "2025-01-01", "--end", "2025-02-01",
            "--types", "ohlcv,funding_rate",
        ])
        assert args.types == "ohlcv,funding_rate"

    def test_list_types_flag(self):
        args = parse_args(["--list-types"])
        assert args.list_types is True


# ------------------------------------------------------------------ #
#  fetch_and_save                                                      #
# ------------------------------------------------------------------ #


class TestFetchAndSave:
    def test_saves_csv(self, tmp_path):
        mock_source = MagicMock()
        mock_df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2025-01-01", "2025-01-02"]),
            "open": [50000.0, 51000.0],
            "high": [51000.0, 52000.0],
            "low": [49000.0, 50000.0],
            "close": [50500.0, 51500.0],
            "volume": [100.0, 200.0],
        })
        mock_source.fetch.return_value = mock_df

        result = fetch_and_save(
            "binance", mock_source, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", DataType.OHLCV, tmp_path,
        )

        assert result is not None
        assert result.exists()
        assert result.suffix == ".csv"
        assert "btcusdt" in result.name
        assert "ohlcv" in result.name
        assert "binance" in result.name

    def test_empty_df_returns_none(self, tmp_path):
        mock_source = MagicMock()
        mock_source.fetch.return_value = pd.DataFrame()

        result = fetch_and_save(
            "binance", mock_source, "BTCUSDT", "2025-01-01", "2025-01-02",
            "1h", "1h", DataType.OHLCV, tmp_path,
        )

        assert result is None


# ------------------------------------------------------------------ #
#  main                                                                #
# ------------------------------------------------------------------ #


class TestMain:
    def test_list_types_returns_zero(self, capsys):
        ret = main(["--list-types"])
        assert ret == 0
        captured = capsys.readouterr()
        assert "ohlcv" in captured.out

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

        with patch("export_data.create_source") as mock_create:
            instance = MagicMock()
            instance.fetch.return_value = mock_df
            mock_create.return_value = instance

            ret = main([
                "--symbol", "BTCUSDT",
                "--start", "2025-01-01",
                "--end", "2025-02-01",
                "--types", "ohlcv",
                "--output-dir", str(tmp_path),
            ])

        assert ret == 0
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1
        assert "ohlcv" in csv_files[0].name
