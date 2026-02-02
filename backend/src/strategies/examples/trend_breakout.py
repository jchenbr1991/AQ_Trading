# backend/src/strategies/examples/trend_breakout.py
"""TrendBreakout strategy combining momentum and breakout factors.

This strategy uses a composite factor score derived from:
- Momentum Factor: ROC and Price vs MA indicators
- Breakout Factor: Price vs High and Volume Z-Score indicators

Entry signal: composite > entry_threshold AND no position
Exit signal: composite < exit_threshold AND has position

Implements:
- FR-013: Composite factor triggers entry/exit
- FR-014: Configurable entry/exit thresholds
- FR-015: Equal-weight position sizing
- FR-016: Fixed-risk position sizing
- FR-017: Strategy generates signals based on factor thresholds
- FR-021: Same logic for backtest/paper/live modes
- FR-023/FR-025: Factor scores stored in Signal for attribution

Supports two weight calculation methods (configurable via weight_method):
- "manual": Use static factor_weights from config
- "ic": Data-driven IC (Information Coefficient) based weighting
"""

import logging
from collections import defaultdict
from decimal import Decimal
from typing import Any, Literal

from src.backtest.ic_weight_calculator import ICWeightCalculator
from src.strategies.base import MarketData, OrderFill, Strategy
from src.strategies.context import StrategyContext
from src.strategies.factors import BreakoutFactor, CompositeFactor, MomentumFactor
from src.strategies.indicators import ROC, PriceVsHigh, PriceVsMA, Volatility, VolumeZScore
from src.strategies.signals import Signal

logger = logging.getLogger(__name__)


class TrendBreakoutStrategy(Strategy):
    """
    Trend/Breakout strategy combining momentum and breakout factors.

    FR-013: Composite factor triggers entry/exit
    FR-014: entry_threshold and exit_threshold configurable
    FR-017: Strategy generates signals based on factor thresholds
    FR-021: Same logic for backtest/paper/live modes

    Attributes:
        name: Strategy identifier.
        symbols: List of symbols to trade.
        entry_threshold: Composite score threshold for entry signals.
        exit_threshold: Composite score threshold for exit signals.
        position_sizing: Mode - "equal_weight" or "fixed_risk".
        position_size: Fixed number of shares (equal_weight mode).
        risk_per_trade: Risk percentage per trade (fixed_risk mode).
    """

    # Default lookback period for all indicators (per spec)
    DEFAULT_LOOKBACK = 20

    def __init__(
        self,
        name: str,
        symbols: list[str],
        entry_threshold: float = 0.0,
        exit_threshold: float = -0.02,
        position_sizing: Literal["equal_weight", "fixed_risk"] = "equal_weight",
        position_size: int = 100,
        risk_per_trade: float = 0.02,
        feature_weights: dict[str, float] | None = None,
        factor_weights: dict[str, float] | None = None,
        weight_method: Literal["manual", "ic"] = "manual",
        ic_weight_config: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        """Initialize TrendBreakout strategy.

        Args:
            name: Strategy identifier.
            symbols: List of symbols to trade.
            entry_threshold: Composite score to trigger buy. Default: 0.0
            exit_threshold: Composite score to trigger sell. Default: -0.02
            position_sizing: "equal_weight" (fixed shares) or "fixed_risk" (volatility-based).
            position_size: Shares per position for equal_weight mode. Default: 100
            risk_per_trade: Risk percentage for fixed_risk mode. Default: 0.02 (2%)
            feature_weights: Weights for indicators (roc_20, price_vs_ma_20, etc.)
            factor_weights: Weights for factors (momentum_factor, breakout_factor)
            weight_method: "manual" (use factor_weights) or "ic" (data-driven IC weighting)
            ic_weight_config: Configuration for IC weight calculator (lookback_window, ewma_span, etc.)
            **kwargs: Additional parameters (ignored).
        """
        self.name = name
        self.symbols = symbols
        self.entry_threshold = Decimal(str(entry_threshold))
        self.exit_threshold = Decimal(str(exit_threshold))
        self.position_sizing = position_sizing
        self.position_size = position_size
        self.risk_per_trade = Decimal(str(risk_per_trade))
        self.weight_method = weight_method

        # Parse weights with defaults
        feature_weights = feature_weights or {}
        factor_weights = factor_weights or {}

        # Extract feature weights (indicator -> factor weights)
        roc_weight = Decimal(str(feature_weights.get("roc_20", 0.5)))
        price_vs_ma_weight = Decimal(str(feature_weights.get("price_vs_ma_20", 0.5)))
        price_vs_high_weight = Decimal(str(feature_weights.get("price_vs_high_20", 0.5)))
        volume_zscore_weight = Decimal(str(feature_weights.get("volume_zscore", 0.5)))

        # Extract factor weights (factor -> composite weights)
        # These are initial weights; may be overridden by IC weighting
        momentum_weight = Decimal(str(factor_weights.get("momentum_factor", 0.5)))
        breakout_weight = Decimal(str(factor_weights.get("breakout_factor", 0.5)))

        # Store manual weights for fallback
        self._manual_factor_weights = {
            "momentum_factor": momentum_weight,
            "breakout_factor": breakout_weight,
        }

        # Initialize IC weight calculator if using IC method
        self._ic_calculator: ICWeightCalculator | None = None
        self._ic_weights_initialized = False
        if weight_method == "ic":
            ic_config = ic_weight_config or {}
            self._ic_calculator = ICWeightCalculator(
                lookback_window=ic_config.get("lookback_window", 60),
                ewma_span=ic_config.get("ewma_span"),
                ic_history_periods=ic_config.get("ic_history_periods", 12),
            )
            logger.info(
                f"[{name}] Using IC-based weight calculation: "
                f"lookback={self._ic_calculator.lookback_window}, "
                f"ewma_span={self._ic_calculator.ewma_span}, "
                f"ic_history_periods={self._ic_calculator.ic_history_periods}"
            )

        # Initialize indicators (T019: Indicator management)
        self._roc = ROC(lookback=self.DEFAULT_LOOKBACK)
        self._price_vs_ma = PriceVsMA(lookback=self.DEFAULT_LOOKBACK)
        self._price_vs_high = PriceVsHigh(lookback=self.DEFAULT_LOOKBACK)
        self._volume_zscore = VolumeZScore(lookback=self.DEFAULT_LOOKBACK)
        self._volatility = Volatility(lookback=self.DEFAULT_LOOKBACK)

        # Initialize factors with configured weights
        self._momentum_factor = MomentumFactor(
            roc_weight=roc_weight,
            price_vs_ma_weight=price_vs_ma_weight,
        )
        self._breakout_factor = BreakoutFactor(
            price_vs_high_weight=price_vs_high_weight,
            volume_zscore_weight=volume_zscore_weight,
        )
        self._composite_factor = CompositeFactor(
            momentum_weight=momentum_weight,
            breakout_weight=breakout_weight,
        )

        # T019: Per-symbol history buffers for indicator calculation
        # Using fixed-size windows per research.md Q3 pattern
        self._price_history: dict[str, list[Decimal]] = defaultdict(list)
        self._volume_history: dict[str, list[int]] = defaultdict(list)
        self._high_history: dict[str, list[Decimal]] = defaultdict(list)

        # Maximum lookback needed for any indicator
        # ROC, PriceVsHigh, VolumeZScore, Volatility all need lookback + 1
        self._max_history_size = self.DEFAULT_LOOKBACK + 1

        # IC weight calculation history (per-symbol)
        # Stores factor scores and forward returns for IC calculation
        self._factor_score_history: dict[str, dict[str, list[Decimal]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._return_history: dict[str, list[Decimal]] = defaultdict(list)
        self._last_price: dict[str, Decimal] = {}

        # Current dynamic factor weights (updated via IC calculation)
        self._dynamic_factor_weights: dict[str, Decimal] = self._manual_factor_weights.copy()

    @property
    def warmup_bars(self) -> int:
        """T020: Number of historical bars needed before generating valid signals.

        The ROC, PriceVsHigh, VolumeZScore, and Volatility indicators all need
        lookback + 1 bars (21 bars for lookback=20). We use 21 to be safe.

        However, the spec says "20 bars" so we return 20 as per T020.
        The actual indicator warmup is handled internally.
        """
        return self.DEFAULT_LOOKBACK

    async def on_market_data(
        self, data: MarketData, context: StrategyContext
    ) -> list[Signal]:
        """Process market data and generate signals.

        Updates indicator buffers, calculates factors, and generates
        entry/exit signals based on composite score thresholds.

        Args:
            data: New market data for a subscribed symbol.
            context: Read-only view of portfolio and quotes.

        Returns:
            List of signals (empty if no action needed).
        """
        signals: list[Signal] = []

        # T019: Update history buffers for this symbol
        self._update_history_buffers(data)

        # Get history for calculations
        prices = self._price_history[data.symbol]
        volumes = self._volume_history[data.symbol]
        highs = self._high_history[data.symbol]

        # Check warmup - need enough data for all indicators
        # The indicators with maximum requirement need lookback + 1 = 21 bars
        if len(prices) < self._max_history_size:
            logger.debug(
                f"[{self.name}] {data.symbol}: Warmup in progress "
                f"({len(prices)}/{self._max_history_size} bars)"
            )
            return []

        # Calculate all indicator values
        indicators = self._calculate_indicators(prices, volumes, highs)

        # If any indicator is None, we can't calculate factors
        if any(v is None for v in indicators.values()):
            logger.debug(
                f"[{self.name}] {data.symbol}: Indicator calculation incomplete"
            )
            return []

        # Calculate factor scores
        factors = self._calculate_factors(indicators)

        # If any factor is None, we can't generate signals
        if factors is None:
            logger.debug(
                f"[{self.name}] {data.symbol}: Factor calculation failed"
            )
            return []

        momentum_score, breakout_score, composite_score = factors

        # Update IC weight history if using IC-based weighting
        if self.weight_method == "ic":
            self._update_ic_weight_history(
                data.symbol, data.price, momentum_score, breakout_score
            )
            # Periodically update weights (every bar - could be optimized)
            self._maybe_update_ic_weights()

        # T052: Log factor scores at DEBUG level for attribution tracking
        logger.debug(
            f"[{self.name}] {data.symbol} @ {data.price}: "
            f"momentum={momentum_score:.4f}, breakout={breakout_score:.4f}, "
            f"composite={composite_score:.4f}"
        )

        # Get current position for this symbol
        position = await context.get_position(data.symbol)
        has_position = position is not None and position.quantity > 0

        # T052: Log position state at DEBUG level
        if has_position:
            logger.debug(
                f"[{self.name}] {data.symbol}: Current position "
                f"qty={position.quantity}, avg_cost={position.avg_cost}"
            )

        # T021: Prepare factor_scores for attribution (FR-023/FR-025)
        factor_scores = {
            "momentum_factor": momentum_score,
            "breakout_factor": breakout_score,
            "composite": composite_score,
        }

        # Generate entry signal if composite > entry_threshold and no position
        if not has_position and composite_score > self.entry_threshold:
            quantity = self._calculate_position_size(data, prices)
            signals.append(
                Signal(
                    strategy_id=self.name,
                    symbol=data.symbol,
                    action="buy",
                    quantity=quantity,
                    reason=(
                        f"Entry: composite {composite_score:.4f} > "
                        f"threshold {self.entry_threshold:.4f}"
                    ),
                    factor_scores=factor_scores,
                )
            )
            # T052: INFO level for signal generation (key events)
            logger.info(
                f"[{self.name}] BUY signal for {data.symbol}: "
                f"composite={composite_score:.4f}, qty={quantity}, "
                f"price={data.price}"
            )
            # T052: DEBUG level for attribution details
            logger.debug(
                f"[{self.name}] BUY attribution factors: "
                f"momentum={momentum_score:.4f} ({float(momentum_score)*100:.1f}%), "
                f"breakout={breakout_score:.4f} ({float(breakout_score)*100:.1f}%)"
            )

        # Generate exit signal if composite < exit_threshold and has position
        elif has_position and composite_score < self.exit_threshold:
            signals.append(
                Signal(
                    strategy_id=self.name,
                    symbol=data.symbol,
                    action="sell",
                    quantity=position.quantity,
                    reason=(
                        f"Exit: composite {composite_score:.4f} < "
                        f"threshold {self.exit_threshold:.4f}"
                    ),
                    factor_scores=factor_scores,
                )
            )
            # T052: INFO level for signal generation (key events)
            logger.info(
                f"[{self.name}] SELL signal for {data.symbol}: "
                f"composite={composite_score:.4f}, qty={position.quantity}, "
                f"price={data.price}"
            )
            # T052: DEBUG level for attribution details
            logger.debug(
                f"[{self.name}] SELL attribution factors: "
                f"momentum={momentum_score:.4f} ({float(momentum_score)*100:.1f}%), "
                f"breakout={breakout_score:.4f} ({float(breakout_score)*100:.1f}%)"
            )

        return signals

    def _update_history_buffers(self, data: MarketData) -> None:
        """T019: Update price/volume/high history buffers for a symbol.

        Maintains fixed-size windows for indicator calculations.
        Pattern from research.md Q3.

        Args:
            data: Market data with price, volume, and (assumed) high.
        """
        symbol = data.symbol

        # Append new values
        self._price_history[symbol].append(data.price)
        self._volume_history[symbol].append(data.volume)

        # For high, use bid as proxy if MarketData doesn't have high
        # In backtest mode, the engine provides bar.high via a custom mechanism
        # For live/paper, we use price as the high (daily close approximation)
        # This is a simplification - real implementation would need OHLCV data
        high_value = getattr(data, "high", data.price)
        if isinstance(high_value, (int, float)):
            high_value = Decimal(str(high_value))
        self._high_history[symbol].append(high_value)

        # Maintain fixed-size windows
        if len(self._price_history[symbol]) > self._max_history_size:
            self._price_history[symbol].pop(0)
        if len(self._volume_history[symbol]) > self._max_history_size:
            self._volume_history[symbol].pop(0)
        if len(self._high_history[symbol]) > self._max_history_size:
            self._high_history[symbol].pop(0)

    def _calculate_indicators(
        self,
        prices: list[Decimal],
        volumes: list[int],
        highs: list[Decimal],
    ) -> dict[str, Decimal | None]:
        """Calculate all technical indicators from history buffers.

        Args:
            prices: Price history (oldest first).
            volumes: Volume history (oldest first).
            highs: High price history (oldest first).

        Returns:
            Dictionary of indicator name to value (may be None during warmup).
        """
        return {
            "roc_20": self._roc.calculate(prices),
            "price_vs_ma_20": self._price_vs_ma.calculate(prices),
            "price_vs_high_20": self._price_vs_high.calculate(prices, highs=highs),
            "volume_zscore": self._volume_zscore.calculate(prices, volumes=volumes),
        }

    def _calculate_factors(
        self,
        indicators: dict[str, Decimal | None],
    ) -> tuple[Decimal, Decimal, Decimal] | None:
        """Calculate factor scores from indicator values.

        Args:
            indicators: Dictionary of indicator values.

        Returns:
            Tuple of (momentum_score, breakout_score, composite_score),
            or None if any factor calculation fails.
        """
        # Calculate momentum factor
        momentum_result = self._momentum_factor.calculate(indicators)
        if momentum_result is None:
            return None

        # Calculate breakout factor
        breakout_result = self._breakout_factor.calculate(indicators)
        if breakout_result is None:
            return None

        # Calculate composite factor
        composite_input = {
            "momentum_factor": momentum_result.score,
            "breakout_factor": breakout_result.score,
        }
        composite_result = self._composite_factor.calculate(composite_input)
        if composite_result is None:
            return None

        return (
            momentum_result.score,
            breakout_result.score,
            composite_result.score,
        )

    def _update_ic_weight_history(
        self,
        symbol: str,
        current_price: Decimal,
        momentum_score: Decimal,
        breakout_score: Decimal,
    ) -> None:
        """Update history for IC weight calculation.

        Stores factor scores and calculates forward returns for IC calculation.
        Called after each bar to accumulate data for weight optimization.

        Args:
            symbol: Trading symbol.
            current_price: Current bar's price.
            momentum_score: Current momentum factor score.
            breakout_score: Current breakout factor score.
        """
        if self._ic_calculator is None:
            return

        # Calculate forward return if we have a previous price
        if symbol in self._last_price:
            prev_price = self._last_price[symbol]
            if prev_price != Decimal("0"):
                forward_return = (current_price - prev_price) / prev_price
                self._return_history[symbol].append(forward_return)

        # Store factor scores (shifted by 1 to align with forward returns)
        # On bar N: we record factor scores from bar N-1 with return from N-1 to N
        self._factor_score_history[symbol]["momentum_factor"].append(momentum_score)
        self._factor_score_history[symbol]["breakout_factor"].append(breakout_score)

        # Update last price
        self._last_price[symbol] = current_price

        # Limit history size to required lookback + buffer
        max_history = self._ic_calculator.lookback_window + self._ic_calculator.ic_history_periods + 10
        for key in self._factor_score_history[symbol]:
            if len(self._factor_score_history[symbol][key]) > max_history:
                self._factor_score_history[symbol][key].pop(0)
        if len(self._return_history[symbol]) > max_history:
            self._return_history[symbol].pop(0)

    def _maybe_update_ic_weights(self) -> None:
        """Update factor weights using IC calculation if enough data.

        Calculates IC-based weights per symbol using the full pipeline,
        then averages weights across symbols for robustness.

        Weight updates are throttled to reduce churn - only recalculates
        when enough new data has accumulated (lookback_window / 4 new bars).
        """
        if self._ic_calculator is None:
            return

        required_data = self._ic_calculator.lookback_window + self._ic_calculator.ic_history_periods

        # Throttle updates: only recalculate every N bars (lookback / 4)
        update_interval = max(self._ic_calculator.lookback_window // 4, 10)
        total_returns = sum(len(self._return_history.get(s, [])) for s in self.symbols)

        # Skip update if not enough new data since last update
        if hasattr(self, "_last_ic_update_count"):
            bars_since_update = total_returns - self._last_ic_update_count
            if bars_since_update < update_interval and self._ic_weights_initialized:
                return
        self._last_ic_update_count = total_returns

        # Calculate weights per symbol, then average
        symbol_weights: dict[str, dict[str, Decimal]] = {}

        for symbol in self.symbols:
            momentum_history = self._factor_score_history[symbol].get("momentum_factor", [])
            breakout_history = self._factor_score_history[symbol].get("breakout_factor", [])
            return_history = self._return_history.get(symbol, [])

            # Align lengths (factor scores at t predict returns at t+1)
            min_len = min(len(momentum_history), len(breakout_history), len(return_history) + 1)

            if min_len < required_data:
                continue  # Not enough data for this symbol

            # Use aligned data for this symbol only
            aligned_momentum = momentum_history[: min_len - 1]
            aligned_breakout = breakout_history[: min_len - 1]
            aligned_returns = return_history[: min_len - 1]

            try:
                factor_history = {
                    "momentum_factor": aligned_momentum,
                    "breakout_factor": aligned_breakout,
                }
                weights = self._ic_calculator.calculate_weights_full_pipeline(
                    factor_history, aligned_returns
                )
                symbol_weights[symbol] = weights
            except Exception as e:
                logger.debug(f"[{self.name}] IC weight calc failed for {symbol}: {e}")

        if not symbol_weights:
            logger.debug(
                f"[{self.name}] IC weight update: insufficient data for all symbols"
            )
            return

        # Average weights across symbols
        momentum_sum = sum(w.get("momentum_factor", Decimal("0")) for w in symbol_weights.values())
        breakout_sum = sum(w.get("breakout_factor", Decimal("0")) for w in symbol_weights.values())
        n_symbols = Decimal(len(symbol_weights))

        momentum_weight = momentum_sum / n_symbols
        breakout_weight = breakout_sum / n_symbols

        # Normalize to sum to 1
        total = momentum_weight + breakout_weight
        if total > Decimal("0"):
            momentum_weight = momentum_weight / total
            breakout_weight = breakout_weight / total

        # Update composite factor weights
        self._composite_factor.update_weights(
            momentum_weight=momentum_weight,
            breakout_weight=breakout_weight,
        )

        self._dynamic_factor_weights = {
            "momentum_factor": momentum_weight,
            "breakout_factor": breakout_weight,
        }
        self._ic_weights_initialized = True

        logger.info(
            f"[{self.name}] IC weights updated (from {len(symbol_weights)} symbols): "
            f"momentum={float(momentum_weight):.3f}, "
            f"breakout={float(breakout_weight):.3f}"
        )

    def _calculate_position_size(
        self,
        data: MarketData,
        prices: list[Decimal],
    ) -> int:
        """T017/T018: Calculate position size based on sizing mode.

        Args:
            data: Current market data with price.
            prices: Price history for volatility calculation.

        Returns:
            Number of shares to trade.
        """
        if self.position_sizing == "equal_weight":
            # T017: Equal-weight sizing - fixed number of shares
            return self.position_size
        else:
            # T018: Fixed-risk sizing based on volatility
            return self._calculate_fixed_risk_size(data.price, prices)

    def _calculate_fixed_risk_size(
        self,
        current_price: Decimal,
        prices: list[Decimal],
    ) -> int:
        """T018: Calculate position size for fixed-risk mode.

        Position size = (risk_capital) / (price * volatility)
        Where:
        - risk_capital = notional_value * risk_per_trade
        - volatility = standard deviation of returns

        This sizes the position such that a 1-sigma move would result
        in a loss equal to risk_per_trade percentage.

        Args:
            current_price: Current price of the asset.
            prices: Price history for volatility calculation.

        Returns:
            Number of shares to trade.
        """
        # Calculate volatility using the Volatility indicator
        volatility = self._volatility.calculate(prices)

        if volatility is None or volatility == Decimal("0"):
            # Fallback to equal_weight if volatility can't be calculated
            logger.warning(
                f"[{self.name}] Cannot calculate volatility, "
                f"falling back to equal_weight sizing"
            )
            return self.position_size

        # Assume a notional account size for position sizing
        # In real implementation, this would come from portfolio context
        # For now, use a fixed notional value based on position_size * price
        notional_base = Decimal(str(self.position_size)) * current_price

        # Risk capital = notional * risk_per_trade
        risk_capital = notional_base * self.risk_per_trade

        # Position value = risk_capital / volatility
        # This means a 1-sigma move = risk_per_trade of our position value
        position_value = risk_capital / volatility

        # Number of shares = position_value / price
        if current_price == Decimal("0"):
            return self.position_size

        shares = position_value / current_price

        # Round down to integer shares, minimum 1
        result = max(1, int(shares))

        logger.debug(
            f"[{self.name}] Fixed-risk sizing: vol={volatility:.4f}, "
            f"risk_cap={risk_capital:.2f}, shares={result}"
        )

        return result

    async def on_fill(self, fill: OrderFill) -> None:
        """Handle order fill notification.

        Logs fill information for monitoring.

        Args:
            fill: Order fill details.
        """
        # T052: INFO level for fills (key position change events)
        logger.info(
            f"[{self.name}] FILL: {fill.action} {fill.quantity} "
            f"{fill.symbol} @ {fill.price}"
        )
        # T052: DEBUG level for fill details
        logger.debug(
            f"[{self.name}] Fill details - symbol={fill.symbol}, "
            f"action={fill.action}, qty={fill.quantity}, "
            f"price={fill.price}, timestamp={getattr(fill, 'timestamp', 'N/A')}"
        )

    async def on_start(self) -> None:
        """Initialize strategy state when started.

        Clears all history buffers for clean start.
        """
        # T052: INFO level for lifecycle events
        logger.info(
            f"[{self.name}] STARTING strategy with symbols: {self.symbols}"
        )
        logger.debug(
            f"[{self.name}] Configuration: "
            f"entry_threshold={self.entry_threshold}, "
            f"exit_threshold={self.exit_threshold}, "
            f"position_sizing={self.position_sizing}, "
            f"position_size={self.position_size}"
        )
        self._price_history.clear()
        self._volume_history.clear()
        self._high_history.clear()

        # Reset IC weight calculation state
        self._factor_score_history.clear()
        self._return_history.clear()
        self._last_price.clear()
        self._ic_weights_initialized = False
        if hasattr(self, "_last_ic_update_count"):
            delattr(self, "_last_ic_update_count")

        # Reset to manual weights
        self._dynamic_factor_weights = self._manual_factor_weights.copy()
        self._composite_factor.update_weights(
            momentum_weight=self._manual_factor_weights["momentum_factor"],
            breakout_weight=self._manual_factor_weights["breakout_factor"],
        )

        logger.debug(f"[{self.name}] All history buffers cleared (including IC state)")

    async def on_stop(self) -> None:
        """Cleanup when strategy stops."""
        # T052: INFO level for lifecycle events
        # Log summary statistics before stopping
        total_symbols = len(self._price_history)
        total_bars = sum(len(h) for h in self._price_history.values())
        logger.info(
            f"[{self.name}] STOPPING - processed {total_bars} total bars "
            f"across {total_symbols} symbols"
        )
