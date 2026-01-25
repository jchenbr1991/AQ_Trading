"""Bar loader implementations for backtesting."""

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from src.backtest.models import Bar


class BarLoader(Protocol):
    """Protocol for loading historical bars."""

    async def load(self, symbol: str, start_date: date, end_date: date) -> list[Bar]:
        """Load bars for symbol within date range.

        Args:
            symbol: Ticker symbol to load (e.g., "AAPL").
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of Bar objects sorted ascending by timestamp.
        """
        ...


class CSVBarLoader:
    """Loads bars from a CSV file.

    Expected CSV format:
    timestamp,symbol,open,high,low,close,volume
    2025-01-02T21:00:00+00:00,AAPL,150.00,152.00,149.00,151.00,1000000

    The timestamp must be ISO 8601 format with timezone info.
    """

    def __init__(self, csv_path: Path | str) -> None:
        """Initialize the loader with path to CSV file.

        Args:
            csv_path: Path to the CSV file containing bar data.
        """
        self._csv_path = Path(csv_path)

    async def load(self, symbol: str, start_date: date, end_date: date) -> list[Bar]:
        """Load bars for symbol within date range, sorted ascending by timestamp.

        Args:
            symbol: Ticker symbol to load (e.g., "AAPL").
            start_date: Start of date range (inclusive).
            end_date: End of date range (inclusive).

        Returns:
            List of Bar objects sorted ascending by timestamp.
            Returns empty list if symbol not found or no bars in range.
        """
        bars: list[Bar] = []

        with open(self._csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Skip rows for different symbols
                if row["symbol"] != symbol:
                    continue

                # Parse timestamp (ISO 8601 format with timezone)
                timestamp = datetime.fromisoformat(row["timestamp"])

                # Filter by date range (inclusive on both ends)
                bar_date = timestamp.date()
                if bar_date < start_date or bar_date > end_date:
                    continue

                bar = Bar(
                    symbol=row["symbol"],
                    timestamp=timestamp,
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=int(row["volume"]),
                )
                bars.append(bar)

        # Sort by timestamp ascending (oldest first)
        bars.sort(key=lambda b: b.timestamp)

        return bars
