#!/usr/bin/env python3
"""Fetch Binance Futures data and export as CSV to data/binance/.

Usage examples:
    # Fetch all data types for BTCUSDT, 2025-01 to 2025-02
    uv run scripts/export_binance_data.py --symbol BTCUSDT --start 2025-01-01 --end 2025-02-01

    # Fetch only klines and funding rate
    uv run scripts/export_binance_data.py --symbol BTCUSDT --start 2025-01-01 --end 2025-02-01 \
        --types klines,funding_rate

    # Fetch with custom intervals
    uv run scripts/export_binance_data.py --symbol ETHUSDT --start 2025-01-01 --end 2025-02-01 \
        --interval 4h --period 4h

    # List available data types
    uv run scripts/export_binance_data.py --list-types
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from binance_client import BinanceFuturesClient

DATA_DIR = Path("data/binance")

# Data types that use kline interval
KLINE_TYPES = {"klines", "index_price", "mark_price"}

# Data types that use analytics period
ANALYTICS_TYPES = {
    "funding_rate",
    "open_interest",
    "long_short_ratio",
    "top_ls_accounts",
    "top_ls_positions",
    "taker_buy_sell",
}

ALL_TYPES = sorted(KLINE_TYPES | ANALYTICS_TYPES)

KLINE_INTERVALS = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

ANALYTICS_PERIODS = ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]


def make_filename(symbol: str, data_type: str, interval_or_period: str | None) -> str:
    """Generate output filename with timestamp prefix.

    Format: yyyymmdd_hhmm_[symbol]_[interval]_[data_type].csv
    """
    now = datetime.now()
    prefix = now.strftime("%Y%m%d_%H%M")
    sym = symbol.lower()

    if interval_or_period:
        return f"{prefix}_{sym}_{interval_or_period}_{data_type}.csv"
    return f"{prefix}_{sym}_{data_type}.csv"


def fetch_and_save(
    client: BinanceFuturesClient,
    symbol: str,
    start: str,
    end: str,
    interval: str,
    period: str,
    data_type: str,
    output_dir: Path,
) -> Path | None:
    """Fetch a single data type and save to CSV. Returns the output path."""
    fetchers = {
        "klines": lambda: (
            client.get_klines(symbol, interval, start, end),
            interval,
        ),
        "index_price": lambda: (
            client.get_index_price_klines(symbol, interval, start, end),
            interval,
        ),
        "mark_price": lambda: (
            client.get_mark_price_klines(symbol, interval, start, end),
            interval,
        ),
        "funding_rate": lambda: (
            client.get_funding_rate_history(symbol, start, end),
            None,
        ),
        "open_interest": lambda: (
            client.get_open_interest_history(symbol, period, start, end),
            period,
        ),
        "long_short_ratio": lambda: (
            client.get_long_short_ratio(symbol, period, start, end),
            period,
        ),
        "top_ls_accounts": lambda: (
            client.get_top_trader_long_short_ratio_accounts(symbol, period, start, end),
            period,
        ),
        "top_ls_positions": lambda: (
            client.get_top_trader_long_short_ratio_positions(symbol, period, start, end),
            period,
        ),
        "taker_buy_sell": lambda: (
            client.get_taker_buy_sell_ratio(symbol, period, start, end),
            period,
        ),
    }

    if data_type not in fetchers:
        print(f"  Unknown data type: {data_type}")
        return None

    df, suffix = fetchers[data_type]()

    if df.empty:
        print(f"  No data returned for {data_type}")
        return None

    filename = make_filename(symbol, data_type, suffix)
    filepath = output_dir / filename
    df.to_csv(filepath, index=False)
    return filepath


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Binance Futures data and export as CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available data types: {', '.join(ALL_TYPES)}",
    )
    parser.add_argument(
        "--symbol", help="Trading pair (e.g. BTCUSDT)"
    )
    parser.add_argument(
        "--start", help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end", help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--interval", default="1h",
        help=f"Kline interval (default: 1h). Options: {', '.join(KLINE_INTERVALS)}",
    )
    parser.add_argument(
        "--period", default="1h",
        help=f"Analytics period (default: 1h). Options: {', '.join(ANALYTICS_PERIODS)}",
    )
    parser.add_argument(
        "--types",
        default=None,
        help="Comma-separated data types to fetch (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATA_DIR),
        help=f"Output directory (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--list-types",
        action="store_true",
        help="List available data types and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_types:
        print("Available data types:")
        print(f"  Kline types (use --interval):    {', '.join(sorted(KLINE_TYPES))}")
        print(f"  Analytics types (use --period):   {', '.join(sorted(ANALYTICS_TYPES))}")
        return 0

    if not all([args.symbol, args.start, args.end]):
        print("Error: --symbol, --start, --end are required", file=sys.stderr)
        return 1

    # Parse requested types
    if args.types:
        types_to_fetch = [t.strip() for t in args.types.split(",")]
        invalid = set(types_to_fetch) - set(ALL_TYPES)
        if invalid:
            print(f"Error: Unknown data types: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available: {', '.join(ALL_TYPES)}", file=sys.stderr)
            return 1
    else:
        types_to_fetch = ALL_TYPES

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Binance Futures Data Export")
    print("=" * 60)
    print(f"  Symbol:    {args.symbol}")
    print(f"  Period:    {args.start} ~ {args.end}")
    print(f"  Interval:  {args.interval} (klines)")
    print(f"  Period:    {args.period} (analytics)")
    print(f"  Types:     {', '.join(types_to_fetch)}")
    print(f"  Output:    {output_dir}/")
    print("=" * 60)

    client = BinanceFuturesClient()
    results: list[tuple[str, str, int]] = []  # (type, path, rows)
    errors: list[tuple[str, str]] = []

    for dtype in types_to_fetch:
        print(f"\n>> Fetching {dtype}...")
        try:
            filepath = fetch_and_save(
                client, args.symbol, args.start, args.end,
                args.interval, args.period, dtype, output_dir,
            )
            if filepath:
                # Read line count from file (header + data)
                row_count = sum(1 for _ in open(filepath)) - 1
                results.append((dtype, str(filepath), row_count))
                print(f"   Saved: {filepath} ({row_count} rows)")
            else:
                errors.append((dtype, "No data returned"))
        except Exception as e:
            errors.append((dtype, str(e)))
            print(f"   Error: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if results:
        print(f"\nSuccessfully exported {len(results)} file(s):")
        for dtype, path, rows in results:
            print(f"  {dtype:20s} -> {path} ({rows} rows)")

    if errors:
        print(f"\nFailed {len(errors)} type(s):")
        for dtype, msg in errors:
            print(f"  {dtype:20s} -> {msg}")

    print("=" * 60)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
