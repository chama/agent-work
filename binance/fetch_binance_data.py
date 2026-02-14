#!/usr/bin/env python3
"""
Binance OHLCV Data Retrieval Script
Fetches historical candlestick data from Binance Futures API
"""

import requests
import csv
from datetime import datetime, timedelta
import time
import sys

def fetch_binance_klines(symbol, interval, start_time, end_time, limit=1500):
    """
    Fetch klines/candlestick data from Binance Futures API

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        interval: Timeframe (e.g., '1d', '1h', '15m')
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
        limit: Number of candles per request (max 1500)

    Returns:
        List of kline data
    """
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    all_klines = []

    current_start = start_time
    request_count = 0

    while current_start < end_time:
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': current_start,
            'endTime': end_time,
            'limit': limit
        }

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                print(f"Fetching data from {datetime.fromtimestamp(current_start/1000).strftime('%Y-%m-%d %H:%M:%S')}...")
                response = requests.get(base_url, params=params, timeout=30)
                request_count += 1

                if response.status_code == 200:
                    klines = response.json()

                    if not klines:
                        print("No more data available.")
                        return all_klines

                    all_klines.extend(klines)
                    print(f"Retrieved {len(klines)} candles (Total: {len(all_klines)})")

                    # Update start time to the last candle's close time + 1ms
                    current_start = klines[-1][6] + 1

                    # If we got fewer candles than requested, we've reached the end
                    if len(klines) < limit:
                        return all_klines

                    # Rate limiting: wait a bit between requests
                    time.sleep(0.1)
                    break

                elif response.status_code == 429:
                    wait_time = 2 ** retry_count
                    print(f"Rate limit exceeded. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    retry_count += 1

                else:
                    print(f"Error: HTTP {response.status_code} - {response.text}")
                    return None

            except requests.exceptions.RequestException as e:
                retry_count += 1
                wait_time = 2 ** retry_count
                print(f"Request failed: {e}. Retrying in {wait_time} seconds... (Attempt {retry_count}/{max_retries})")
                time.sleep(wait_time)

        if retry_count >= max_retries:
            print("Max retries reached. Aborting.")
            return None

    return all_klines

def save_to_csv(klines, filename):
    """
    Save klines data to CSV file

    Args:
        klines: List of kline data from Binance API
        filename: Output CSV filename
    """
    if not klines:
        print("No data to save.")
        return False

    # Validate data integrity
    print("\nValidating data integrity...")
    issues = []

    for i, kline in enumerate(klines):
        open_price = float(kline[1])
        high_price = float(kline[2])
        low_price = float(kline[3])
        close_price = float(kline[4])
        volume = float(kline[5])

        # Check OHLC relationships
        if high_price < max(open_price, close_price, low_price):
            issues.append(f"Row {i}: High price is not the highest")
        if low_price > min(open_price, close_price, high_price):
            issues.append(f"Row {i}: Low price is not the lowest")
        if volume < 0:
            issues.append(f"Row {i}: Negative volume")

    if issues:
        print(f"Warning: Found {len(issues)} data integrity issues:")
        for issue in issues[:5]:  # Show first 5 issues
            print(f"  - {issue}")
        if len(issues) > 5:
            print(f"  ... and {len(issues) - 5} more")
    else:
        print("Data integrity check passed!")

    # Write to CSV
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        for kline in klines:
            timestamp = datetime.fromtimestamp(kline[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            open_price = f"{float(kline[1]):.8f}"
            high_price = f"{float(kline[2]):.8f}"
            low_price = f"{float(kline[3]):.8f}"
            close_price = f"{float(kline[4]):.8f}"
            volume = f"{float(kline[5]):.3f}"

            writer.writerow([timestamp, open_price, high_price, low_price, close_price, volume])

    print(f"\nData saved to: {filename}")
    return True

def main():
    # Configuration
    symbols = ['BTCUSDT', 'ETHUSDT']
    timeframe = '1d'

    # Calculate date range: 1 year from today
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    # Convert to milliseconds timestamps
    start_time = int(start_date.timestamp() * 1000)
    end_time = int(end_date.timestamp() * 1000)

    print("=" * 60)
    print("Binance OHLCV Data Retrieval")
    print("=" * 60)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Timeframe: {timeframe}")
    print(f"Start Date: {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"End Date: {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Process each symbol
    for symbol in symbols:
        print(f"\n{'=' * 60}")
        print(f"Processing {symbol}")
        print("=" * 60)

        # Fetch data
        klines = fetch_binance_klines(symbol, timeframe, start_time, end_time)

        if klines is None:
            print(f"\nFailed to fetch data for {symbol} from Binance API.")
            continue

        if not klines:
            print(f"\nNo data retrieved for {symbol}. Please check the symbol and date range.")
            continue

        # Generate filename
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        filename = f"data/{symbol}_{timeframe}_{start_str}_{end_str}.csv"

        # Save to CSV
        if save_to_csv(klines, filename):
            # Print summary
            first_timestamp = datetime.fromtimestamp(klines[0][0] / 1000)
            last_timestamp = datetime.fromtimestamp(klines[-1][0] / 1000)

            print("\n" + "=" * 60)
            print(f"SUMMARY for {symbol}")
            print("=" * 60)
            print(f"Total candles retrieved: {len(klines)}")
            print(f"Actual data range:")
            print(f"  First candle: {first_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"  Last candle: {last_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Output file: {filename}")
            print("=" * 60)
        else:
            print(f"\nFailed to save data to CSV for {symbol}.")

    print("\n" + "=" * 60)
    print("All processing complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
