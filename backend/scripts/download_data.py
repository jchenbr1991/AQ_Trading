#!/usr/bin/env python3
"""Download historical stock data for backtesting."""

from pathlib import Path

import pandas as pd
import yfinance as yf


def download_and_format(symbols: list[str], start: str, end: str, output_path: Path):
    """Download data from Yahoo Finance and format for backtesting.

    Args:
        symbols: List of ticker symbols to download
        start: Start date (YYYY-MM-DD)
        end: End date (YYYY-MM-DD)
        output_path: Path to output CSV file
    """
    all_bars = []

    for symbol in symbols:
        print(f"Downloading {symbol}...")
        df = yf.download(symbol, start=start, end=end, progress=False)

        if df.empty:
            print(f"  Warning: No data for {symbol}")
            continue

        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Reset index to get Date as column
        df = df.reset_index()

        # Format for our CSV loader
        for _, row in df.iterrows():
            # Convert to timezone-aware UTC timestamp
            ts = pd.Timestamp(row["Date"]).tz_localize("America/New_York")
            ts_utc = ts.tz_convert("UTC")

            all_bars.append(
                {
                    "timestamp": ts_utc.isoformat(),
                    "symbol": symbol,
                    "open": f"{row['Open']:.2f}",
                    "high": f"{row['High']:.2f}",
                    "low": f"{row['Low']:.2f}",
                    "close": f"{row['Close']:.2f}",
                    "volume": int(row["Volume"]),
                }
            )

        print(f"  Downloaded {len(df)} bars for {symbol}")

    # Create DataFrame and save
    result_df = pd.DataFrame(all_bars)
    result_df.to_csv(output_path, index=False)
    print(f"\nSaved {len(result_df)} total bars to {output_path}")


if __name__ == "__main__":
    # Configuration
    symbols = ["AAPL", "SPY", "TSLA", "MSFT", "GOOGL"]
    start_date = "2023-01-01"
    end_date = "2025-01-31"

    output_file = Path(__file__).parent.parent / "data" / "bars.csv"

    print(f"Downloading data from {start_date} to {end_date}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Output: {output_file}\n")

    download_and_format(symbols, start_date, end_date, output_file)

    print("\nDone! You can now run backtests.")
