"""Backtest engine for running backtests."""

import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from src.backtest.attribution import AttributionCalculator
from src.backtest.bar_loader import BarLoader
from src.backtest.benchmark import BenchmarkBuilder
from src.backtest.benchmark_metrics import BenchmarkMetrics
from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.metrics import MetricsCalculator
from src.backtest.models import BacktestConfig, BacktestResult, Bar, Trade
from src.backtest.portfolio import BacktestPortfolio
from src.backtest.trace import SignalTrace
from src.backtest.trace_builder import TraceBuilder
from src.strategies.base import MarketData, Strategy
from src.strategies.signals import Signal

if TYPE_CHECKING:
    from src.strategies.context import StrategyContext


class BacktestEngine:
    """Orchestrates backtest execution.

    The engine follows the critical event order to prevent lookahead bias:
    1. Strategy receives MarketData (price = bar[i].close)
    2. Strategy emits Signal (timestamp = bar[i].timestamp)
    3. Signal executes on bar[i+1].open (if exists)

    RULE: When processing bar[i], NEVER read bar[i+1] except to check existence.
    """

    ALLOWED_STRATEGY_PREFIX = "src.strategies."  # Security allowlist

    def __init__(self, bar_loader: BarLoader) -> None:
        """Initialize the backtest engine.

        Args:
            bar_loader: Loader for historical bar data.
        """
        self._bar_loader = bar_loader

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute a complete backtest.

        Args:
            config: Configuration for the backtest run.

        Returns:
            BacktestResult with equity curve, trades, and metrics.

        Raises:
            ValueError: If insufficient bars for strategy warmup.
        """
        started_at = datetime.now(timezone.utc)

        # 1. Instantiate strategy
        strategy = self._create_strategy(config)
        warmup_required = strategy.warmup_bars

        # 2. Load bars with warmup buffer
        # Load extra days to ensure we have enough warmup bars
        # (weekends/holidays mean not every calendar day has a bar)
        data_start = config.start_date - timedelta(days=warmup_required * 3 + 7)
        all_bars = await self._bar_loader.load(
            symbol=config.symbol,
            start_date=data_start,
            end_date=config.end_date,
        )

        # 3. Split warmup/backtest bars
        warmup_bars = [b for b in all_bars if b.timestamp.date() < config.start_date]
        backtest_bars = [b for b in all_bars if b.timestamp.date() >= config.start_date]

        if len(warmup_bars) < warmup_required:
            raise ValueError(
                f"Insufficient warmup data: need {warmup_required}, got {len(warmup_bars)}"
            )

        # 4. Initialize components
        portfolio = BacktestPortfolio(config.initial_capital)
        fill_engine = SimulatedFillEngine(
            slippage_bps=config.slippage_bps,
            commission_per_share=config.commission_per_share,
        )

        equity_curve: list[tuple[datetime, Decimal]] = []
        trades: list[Trade] = []
        first_signal_bar: datetime | None = None

        # Trace tracking for signal-to-fill audit trail
        pending_traces: dict[datetime, SignalTrace] = {}  # keyed by signal_timestamp
        completed_traces: list[SignalTrace] = []

        # Attribution tracking
        attribution_calculator = AttributionCalculator()

        # Extract factor_weights from strategy params for attribution calculation
        # These weights are used by calculate_trade_attribution per FR-023
        raw_factor_weights = config.strategy_params.get("factor_weights", {})
        factor_weights: dict[str, Decimal] | None = None
        if raw_factor_weights:
            factor_weights = {k: Decimal(str(v)) for k, v in raw_factor_weights.items()}
        # Track entry positions for attribution calculation
        # Supports scale-ins (multiple buys) and partial exits
        # Key: symbol, Value: dict with:
        #   - entry_trades: list of (trade, quantity_remaining) tuples
        #   - total_qty: total shares held
        #   - weighted_avg_cost: quantity-weighted average entry price
        #   - weighted_factors: quantity-weighted average factor scores
        pending_entry_positions: dict[str, dict] = {}

        # Prepare bars to process: warmup bars (last N) + backtest bars
        bars_to_process = (
            warmup_bars[-warmup_required:] + backtest_bars if warmup_required > 0 else backtest_bars
        )

        # 5. Event loop
        pending_signal: Signal | None = None

        for bar in bars_to_process:
            is_backtest_phase = bar.timestamp.date() >= config.start_date

            # Execute pending signal at this bar's open
            if pending_signal is not None and is_backtest_phase:
                trade_executed = False
                trade: Trade | None = None
                if pending_signal.action == "buy":
                    if portfolio.can_buy(
                        bar.open,
                        pending_signal.quantity,
                        config.commission_per_share * pending_signal.quantity,
                    ):
                        trade = fill_engine.execute(pending_signal, bar)
                        portfolio.apply_trade(trade)
                        trades.append(trade)
                        trade_executed = True
                        # Track entry trade for attribution (FR-025)
                        # Support scale-ins: accumulate entries with weighted averaging
                        symbol = trade.symbol
                        if symbol not in pending_entry_positions:
                            pending_entry_positions[symbol] = {
                                "entry_trades": [],
                                "total_qty": 0,
                                "weighted_avg_cost": Decimal("0"),
                                "weighted_factors": {},
                                "total_commission": Decimal("0"),
                            }
                        pos = pending_entry_positions[symbol]
                        pos["entry_trades"].append((trade, trade.quantity))
                        old_qty = pos["total_qty"]
                        new_qty = old_qty + trade.quantity
                        # Update weighted average cost
                        if new_qty > 0:
                            pos["weighted_avg_cost"] = (
                                pos["weighted_avg_cost"] * old_qty
                                + trade.fill_price * trade.quantity
                            ) / new_qty
                        # Update weighted factor scores
                        for factor, score in trade.entry_factors.items():
                            old_score = pos["weighted_factors"].get(factor, Decimal("0"))
                            if new_qty > 0:
                                pos["weighted_factors"][factor] = (
                                    old_score * old_qty + score * trade.quantity
                                ) / new_qty
                        pos["total_qty"] = new_qty
                        pos["total_commission"] += trade.commission
                elif pending_signal.action == "sell":
                    if portfolio.can_sell(pending_signal.quantity):
                        trade = fill_engine.execute(pending_signal, bar)
                        # Store exit_factors from the signal (FR-025)
                        trade.exit_factors = dict(pending_signal.factor_scores)
                        portfolio.apply_trade(trade)
                        trades.append(trade)
                        trade_executed = True
                        # Calculate attribution when position is (partially) closed (FR-023)
                        symbol = trade.symbol
                        if symbol in pending_entry_positions:
                            pos = pending_entry_positions[symbol]
                            sell_qty = trade.quantity
                            # Calculate PnL using weighted average cost
                            # Pro-rate entry commission based on sold quantity
                            entry_commission_prorata = (
                                pos["total_commission"] * sell_qty / pos["total_qty"]
                                if pos["total_qty"] > 0
                                else Decimal("0")
                            )
                            pnl = (
                                (trade.fill_price - pos["weighted_avg_cost"]) * sell_qty
                                - trade.commission
                                - entry_commission_prorata
                            )
                            # Calculate attribution using weighted factor scores
                            attribution = attribution_calculator.calculate_trade_attribution(
                                pnl=pnl,
                                entry_factors=pos["weighted_factors"],
                                factor_weights=factor_weights,
                            )
                            trade.attribution = attribution
                            # Update position: reduce quantity and pro-rate commission
                            pos["total_qty"] -= sell_qty
                            pos["total_commission"] -= entry_commission_prorata
                            # Clean up if fully closed
                            if pos["total_qty"] <= 0:
                                del pending_entry_positions[symbol]

                # Complete pending trace if trade was executed
                if trade_executed and pending_signal.timestamp in pending_traces:
                    pending_trace = pending_traces[pending_signal.timestamp]
                    completed_trace = TraceBuilder.complete(
                        pending_trace=pending_trace,
                        fill_bar=bar,
                        fill_price=trade.fill_price,
                        fill_quantity=trade.quantity,
                        commission=trade.commission,
                    )
                    completed_traces.append(completed_trace)
                    del pending_traces[pending_signal.timestamp]

                pending_signal = None

            # Strategy processes bar
            market_data = self._bar_to_market_data(bar)
            context = self._create_backtest_context(portfolio, bar.close)
            signals = await strategy.on_market_data(market_data, context)

            # Capture signal for next bar
            if signals:
                pending_signal = signals[0]
                if first_signal_bar is None:
                    first_signal_bar = bar.timestamp

                # Create pending trace for the signal
                pending_trace = TraceBuilder.create_pending(
                    signal_bar=bar,
                    signal_direction=pending_signal.action,
                    signal_quantity=pending_signal.quantity,
                    signal_reason=pending_signal.reason if pending_signal.reason else None,
                    cash=portfolio.cash,
                    position_qty=portfolio.position_qty,
                    position_avg_cost=portfolio.position_avg_cost
                    if portfolio.position_qty > 0
                    else None,
                    equity=portfolio.equity(bar.close),
                    strategy_snapshot=None,  # MVP: skip strategy snapshot
                )
                pending_traces[pending_signal.timestamp] = pending_trace

            # Record equity (backtest phase only)
            if is_backtest_phase:
                equity = portfolio.equity(bar.close)
                equity_curve.append((bar.timestamp, equity))

        completed_at = datetime.now(timezone.utc)

        # 6. Compute metrics
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=config.initial_capital,
        )

        # 7. Compute benchmark comparison if benchmark_symbol provided
        benchmark = None
        if config.benchmark_symbol:
            benchmark_bars = await self._bar_loader.load(
                config.benchmark_symbol,
                config.start_date,
                config.end_date,
            )
            if benchmark_bars:
                benchmark_curve = BenchmarkBuilder.buy_and_hold(
                    benchmark_bars, config.initial_capital
                )
                benchmark = BenchmarkMetrics.compute(
                    equity_curve, benchmark_curve, config.benchmark_symbol
                )

        # 8. Calculate attribution summary across all trades (FR-023)
        # First, calculate realized attribution from completed trades
        attribution_summary = attribution_calculator.calculate_summary(trades)

        # Include unrealized PnL attribution from open positions if any remain
        # Note: We don't modify Trade objects - unrealized attribution is added
        # directly to the summary to maintain data model integrity
        final_price = backtest_bars[-1].close if backtest_bars else config.initial_capital
        for _symbol, pos in pending_entry_positions.items():
            remaining_qty = pos["total_qty"]
            if remaining_qty > 0:
                # Calculate unrealized PnL using weighted average cost
                # (current_price - weighted_avg_cost) * remaining_qty
                # No exit commission since position is still open
                unrealized_pnl = (final_price - pos["weighted_avg_cost"]) * remaining_qty
                # Calculate attribution for unrealized PnL using weighted entry factors
                unrealized_attribution = attribution_calculator.calculate_trade_attribution(
                    pnl=unrealized_pnl,
                    entry_factors=pos["weighted_factors"],
                    factor_weights=factor_weights,
                )
                # Add unrealized attribution directly to summary
                for factor_name, attr_value in unrealized_attribution.items():
                    if factor_name not in attribution_summary:
                        attribution_summary[factor_name] = Decimal("0")
                    attribution_summary[factor_name] += attr_value
                # Update total if it exists
                if "total" in attribution_summary:
                    attribution_summary["total"] += sum(unrealized_attribution.values())

        # 9. Build and return result
        return BacktestResult(
            config=config,
            equity_curve=equity_curve,
            trades=trades,
            final_equity=equity_curve[-1][1] if equity_curve else config.initial_capital,
            final_cash=portfolio.cash,
            final_position_qty=portfolio.position_qty,
            total_return=metrics["total_return"],
            annualized_return=metrics["annualized_return"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            win_rate=metrics["win_rate"],
            total_trades=metrics["total_trades"],
            avg_trade_pnl=metrics["avg_trade_pnl"],
            warm_up_required_bars=warmup_required,
            warm_up_bars_used=min(len(warmup_bars), warmup_required),
            first_signal_bar=first_signal_bar,
            started_at=started_at,
            completed_at=completed_at,
            benchmark=benchmark,
            traces=completed_traces,
            attribution_summary=attribution_summary,
        )

    def _create_strategy(self, config: BacktestConfig) -> Strategy:
        """Create a strategy instance from config.

        Args:
            config: Backtest configuration with strategy class name.

        Returns:
            Instantiated Strategy object.

        Raises:
            ValueError: If strategy class is not in allowed prefix.
            ImportError: If strategy module cannot be imported.
            AttributeError: If strategy class not found in module.
        """
        strategy_class = config.strategy_class

        # Security check: only allow strategies from approved locations
        # Allow test strategies for testing purposes
        if not (
            strategy_class.startswith(self.ALLOWED_STRATEGY_PREFIX)
            or strategy_class.startswith("tests.")
        ):
            raise ValueError(
                f"Strategy class '{strategy_class}' is not in allowed prefix "
                f"'{self.ALLOWED_STRATEGY_PREFIX}'"
            )

        # Split module path and class name
        module_path, class_name = strategy_class.rsplit(".", 1)

        # Import module and get class
        module = importlib.import_module(module_path)
        strategy_cls = getattr(module, class_name)

        # Instantiate with params
        # Automatically add name and symbols if not provided
        params = dict(config.strategy_params)
        if "name" not in params:
            params["name"] = class_name
        if "symbols" not in params:
            params["symbols"] = [config.symbol]

        return strategy_cls(**params)

    def _bar_to_market_data(self, bar: Bar) -> MarketData:
        """Convert a Bar to MarketData for strategy consumption.

        Uses close price as the current price, and approximates bid/ask.

        Args:
            bar: The historical bar data.

        Returns:
            MarketData object with bar's close price.
        """
        return MarketData(
            symbol=bar.symbol,
            price=bar.close,
            bid=bar.close,  # Approximation for backtest
            ask=bar.close,  # Approximation for backtest
            volume=bar.volume,
            timestamp=bar.timestamp,
        )

    def _create_backtest_context(
        self, portfolio: BacktestPortfolio, current_price: Decimal
    ) -> "StrategyContext":
        """Create a mock StrategyContext for backtest.

        Uses a mock that provides position information from the portfolio.

        Args:
            portfolio: Current portfolio state.
            current_price: Current market price.

        Returns:
            Mock StrategyContext with position data.
        """
        from dataclasses import dataclass
        from unittest.mock import MagicMock

        @dataclass
        class MockPosition:
            quantity: int
            avg_cost: Decimal

        context = MagicMock()

        # Set up get_position to return position data
        async def get_position(symbol: str):
            if portfolio.position_qty > 0:
                return MockPosition(
                    quantity=portfolio.position_qty,
                    avg_cost=portfolio.position_avg_cost,
                )
            return None

        context.get_position = get_position

        return context
