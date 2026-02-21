#!/usr/bin/env python3
"""Fetch futures market data from any supported exchange and export as CSV.

The output CSV schema is determined by the DataType, not the exchange.
This means OHLCV files from Binance, Bybit, OKX, etc. all share the
same column layout, enabling seamless cross-exchange analysis.

Usage examples:
    # Fetch all data types for BTCUSDT from Binance
    uv run scripts/export_data.py --exchange binance --symbol BTCUSDT \
        --start 2025-01-01 --end 2025-02-01

    # Fetch only ohlcv and funding_rate
    uv run scripts/export_data.py --exchange binance --symbol BTCUSDT \
        --start 2025-01-01 --end 2025-02-01 --types ohlcv,funding_rate

    # Custom intervals
    uv run scripts/export_data.py --exchange binance --symbol ETHUSDT \
        --start 2025-01-01 --end 2025-02-01 --interval 4h --period 4h

    # List available data types
    uv run scripts/export_data.py --list-types
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from market_data import DataType, create_source

DATA_DIR = Path("data")


def make_filename(
    exchange: str, symbol: str, data_type: DataType, interval_or_period: str | None,
) -> str:
    """Generate output filename with timestamp prefix.

    Format: yyyymmdd_hhmm_[exchange]_[symbol]_[interval]_[data_type].csv
    """
    now = datetime.now()
    prefix = now.strftime("%Y%m%d_%H%M")
    sym = symbol.lower()
    ex = exchange.lower()

    if interval_or_period:
        return f"{prefix}_{ex}_{sym}_{interval_or_period}_{data_type.value}.csv"
    return f"{prefix}_{ex}_{sym}_{data_type.value}.csv"


def fetch_and_save(
    exchange: str,
    source,
    symbol: str,
    start: str,
    end: str,
    interval: str,
    period: str,
    data_type: DataType,
    output_dir: Path,
) -> Path | None:
    """Fetch a single data type and save to CSV. Returns the output path."""
    suffix = None
    if data_type.uses_interval:
        suffix = interval
    elif data_type.uses_period:
        suffix = period

    df = source.fetch(
        data_type, symbol, start, end,
        interval=interval, period=period,
    )

    if df.empty:
        print(f"  No data returned for {data_type.value}")
        return None

    filename = make_filename(exchange, symbol, data_type, suffix)
    filepath = output_dir / filename
    df.to_csv(filepath, index=False)
    return filepath


ALL_TYPE_VALUES = sorted(dt.value for dt in DataType)

INTERVAL_TYPES = sorted(dt.value for dt in DataType if dt.uses_interval)
PERIOD_TYPES = sorted(dt.value for dt in DataType if dt.uses_period)

KLINE_INTERVALS = [
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
]

ANALYTICS_PERIODS = ["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch futures market data and export as CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Available data types: {', '.join(ALL_TYPE_VALUES)}",
    )
    parser.add_argument(
        "--exchange", default="binance",
        help="Exchange name (default: binance)",
    )
    parser.add_argument("--symbol", help="Trading pair (e.g. BTCUSDT)")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--interval", default="1h",
        help=f"Kline interval (default: 1h). Options: {', '.join(KLINE_INTERVALS)}",
    )
    parser.add_argument(
        "--period", default="1h",
        help=f"Analytics period (default: 1h). Options: {', '.join(ANALYTICS_PERIODS)}",
    )
    parser.add_argument(
        "--types", default=None,
        help="Comma-separated data types to fetch (default: all)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: data/<exchange>/)",
    )
    parser.add_argument(
        "--list-types", action="store_true",
        help="List available data types and exit",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.list_types:
        print("Available data types:")
        print(f"  Interval types (use --interval):  {', '.join(INTERVAL_TYPES)}")
        print(f"  Period types   (use --period):     {', '.join(PERIOD_TYPES)}")
        return 0

    if not all([args.symbol, args.start, args.end]):
        print("Error: --symbol, --start, --end are required", file=sys.stderr)
        return 1

    # Parse requested types
    if args.types:
        type_names = [t.strip() for t in args.types.split(",")]
        invalid = set(type_names) - set(ALL_TYPE_VALUES)
        if invalid:
            print(f"Error: Unknown data types: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available: {', '.join(ALL_TYPE_VALUES)}", file=sys.stderr)
            return 1
        types_to_fetch = [DataType(name) for name in type_names]
    else:
        types_to_fetch = list(DataType)

    output_dir = Path(args.output_dir) if args.output_dir else DATA_DIR / args.exchange
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Futures Market Data Export")
    print("=" * 60)
    print(f"  Exchange:  {args.exchange}")
    print(f"  Symbol:    {args.symbol}")
    print(f"  Period:    {args.start} ~ {args.end}")
    print(f"  Interval:  {args.interval} (klines)")
    print(f"  Period:    {args.period} (analytics)")
    print(f"  Types:     {', '.join(dt.value for dt in types_to_fetch)}")
    print(f"  Output:    {output_dir}/")
    print("=" * 60)

    source = create_source(args.exchange)
    results: list[tuple[str, str, int]] = []
    errors: list[tuple[str, str]] = []

    for dtype in types_to_fetch:
        print(f"\n>> Fetching {dtype.value}...")
        try:
            filepath = fetch_and_save(
                args.exchange, source, args.symbol,
                args.start, args.end,
                args.interval, args.period,
                dtype, output_dir,
            )
            if filepath:
                row_count = sum(1 for _ in open(filepath)) - 1
                results.append((dtype.value, str(filepath), row_count))
                print(f"   Saved: {filepath} ({row_count} rows)")
            else:
                errors.append((dtype.value, "No data returned"))
        except Exception as e:
            errors.append((dtype.value, str(e)))
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
