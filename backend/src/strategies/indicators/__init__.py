# backend/src/strategies/indicators/__init__.py
"""Technical indicators package for strategy calculations.

This module provides technical indicator implementations used by trading strategies
for signal generation and market analysis.

Available Indicators:
- BaseIndicator: Abstract base class for all indicators
- ROC: Rate of Change (momentum)
- PriceVsMA: Price vs Moving Average (momentum)
- PriceVsHigh: Price vs Recent High (breakout)
- VolumeZScore: Volume Z-Score (volume)
- Volatility: Standard deviation of returns (volume/risk)

See specs/002-minimal-mvp-trading/data-model.md for indicator formulas.
"""

from src.strategies.indicators.base import BaseIndicator
from src.strategies.indicators.breakout import PriceVsHigh
from src.strategies.indicators.momentum import ROC, PriceVsMA
from src.strategies.indicators.volume import Volatility, VolumeZScore

__all__: list[str] = [
    "BaseIndicator",
    "ROC",
    "PriceVsMA",
    "PriceVsHigh",
    "VolumeZScore",
    "Volatility",
]
