"""Backtest engine for running backtests."""

import importlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from src.backtest.bar_loader import BarLoader
from src.backtest.benchmark import BenchmarkBuilder
from src.backtest.benchmark_metrics import BenchmarkMetrics
from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.metrics import MetricsCalculator
from src.backtest.models import BacktestConfig, BacktestResult, Bar
from src.backtest.portfolio import BacktestPortfolio
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
        trades: list = []
        first_signal_bar: datetime | None = None

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
                if pending_signal.action == "buy":
                    if portfolio.can_buy(
                        bar.open,
                        pending_signal.quantity,
                        config.commission_per_share * pending_signal.quantity,
                    ):
                        trade = fill_engine.execute(pending_signal, bar)
                        portfolio.apply_trade(trade)
                        trades.append(trade)
                elif pending_signal.action == "sell":
                    if portfolio.can_sell(pending_signal.quantity):
                        trade = fill_engine.execute(pending_signal, bar)
                        portfolio.apply_trade(trade)
                        trades.append(trade)
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

        # 8. Build and return result
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
        return strategy_cls(**config.strategy_params)

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
