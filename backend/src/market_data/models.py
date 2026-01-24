# backend/src/market_data/models.py
"""Market data models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

if TYPE_CHECKING:
    from src.strategies.base import MarketData

ScenarioType = Literal["flat", "trend_up", "trend_down", "volatile", "jump", "stale"]


@dataclass
class QuoteSnapshot:
    """
    Cached quote state with system metadata.

    Distinction from MarketData:
    - MarketData: Event flowing through queue
    - QuoteSnapshot: Cached state with staleness tracking
    """

    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime  # Event-time (from source)
    cached_at: datetime  # System-time (when cached, for debugging)

    def is_stale(self, threshold_ms: int) -> bool:
        """
        Check staleness using event-time, NOT cached_at.

        This ensures correct behavior with delayed/out-of-order data.
        """
        age_ms = (datetime.utcnow() - self.timestamp).total_seconds() * 1000
        return age_ms > threshold_ms

    @classmethod
    def from_market_data(cls, data: "MarketData") -> "QuoteSnapshot":
        """Create QuoteSnapshot from MarketData event."""
        return cls(
            symbol=data.symbol,
            price=data.price,
            bid=data.bid,
            ask=data.ask,
            volume=data.volume,
            timestamp=data.timestamp,
            cached_at=datetime.utcnow(),
        )


@dataclass
class SymbolScenario:
    """Configuration for per-symbol mock data generation."""

    symbol: str
    scenario: ScenarioType
    base_price: Decimal
    tick_interval_ms: int = 100


@dataclass
class FaultConfig:
    """Configuration for fault injection."""

    enabled: bool = False
    delay_probability: float = 0.0
    delay_ms_range: tuple[int, int] = (100, 500)
    duplicate_probability: float = 0.0
    out_of_order_probability: float = 0.0
    out_of_order_offset_ms: int = 200
    stale_window_probability: float = 0.0
    stale_window_duration_ms: tuple[int, int] = (2000, 5000)


@dataclass
class MarketDataConfig:
    """Configuration for MarketDataService."""

    queue_max_size: int = 1000
    default_tick_interval_ms: int = 100
    staleness_threshold_ms: int = 5000
    symbols: dict[str, SymbolScenario] = field(default_factory=dict)
    faults: FaultConfig = field(default_factory=FaultConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "MarketDataConfig":
        """Load configuration from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        md_data = data.get("market_data", {})
        symbols_data = md_data.get("symbols", {})
        faults_data = md_data.get("faults", {})

        symbols = {}
        for symbol, cfg in symbols_data.items():
            symbols[symbol] = SymbolScenario(
                symbol=symbol,
                scenario=cfg["scenario"],
                base_price=Decimal(str(cfg["base_price"])),
                tick_interval_ms=cfg.get("tick_interval_ms", 100),
            )

        faults = FaultConfig(
            enabled=faults_data.get("enabled", False),
            delay_probability=faults_data.get("delay_probability", 0.0),
            delay_ms_range=tuple(faults_data.get("delay_ms_range", [100, 500])),
            duplicate_probability=faults_data.get("duplicate_probability", 0.0),
            out_of_order_probability=faults_data.get("out_of_order_probability", 0.0),
            out_of_order_offset_ms=faults_data.get("out_of_order_offset_ms", 200),
            stale_window_probability=faults_data.get("stale_window_probability", 0.0),
            stale_window_duration_ms=tuple(
                faults_data.get("stale_window_duration_ms", [2000, 5000])
            ),
        )

        return cls(
            queue_max_size=md_data.get("queue_max_size", 1000),
            default_tick_interval_ms=md_data.get("default_tick_interval_ms", 100),
            staleness_threshold_ms=md_data.get("staleness_threshold_ms", 5000),
            symbols=symbols,
            faults=faults,
        )
