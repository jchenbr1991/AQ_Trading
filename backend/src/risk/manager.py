from decimal import Decimal
from typing import Protocol

from src.risk.models import RiskConfig, RiskResult
from src.strategies.signals import Signal


class PortfolioProtocol(Protocol):
    """Protocol for portfolio manager dependency."""

    async def get_account(self, account_id: str): ...
    async def get_positions(self, account_id: str): ...
    async def get_position(self, account_id: str, symbol: str, strategy_id: str): ...


class RiskManager:
    """Validates trading signals against risk limits."""

    def __init__(self, config: RiskConfig, portfolio: PortfolioProtocol):
        self._config = config
        self._portfolio = portfolio
        self._killed = False
        self._kill_reason: str | None = None
        self._paused_strategies: set[str] = set()
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: Decimal = Decimal("0")

    # Emergency controls
    def activate_kill_switch(self, reason: str) -> None:
        """Activate kill switch to block all trading."""
        self._killed = True
        self._kill_reason = reason

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch to resume trading."""
        self._killed = False
        self._kill_reason = None

    def is_killed(self) -> bool:
        """Check if kill switch is active."""
        return self._killed

    # Strategy controls
    def pause_strategy(self, strategy_id: str) -> None:
        """Pause a specific strategy."""
        self._paused_strategies.add(strategy_id)

    def resume_strategy(self, strategy_id: str) -> None:
        """Resume a paused strategy."""
        self._paused_strategies.discard(strategy_id)

    def is_strategy_paused(self, strategy_id: str) -> bool:
        """Check if a strategy is paused."""
        return strategy_id in self._paused_strategies

    def _check_symbol_allowed(self, signal: Signal) -> bool:
        """Check if symbol is allowed to trade."""
        # Blocked list takes precedence
        if signal.symbol in self._config.blocked_symbols:
            return False

        # If allowed list is set, symbol must be in it
        if self._config.allowed_symbols:
            return signal.symbol in self._config.allowed_symbols

        return True

    async def _check_position_limits(self, signal: Signal) -> bool:
        """Check position-level limits."""
        # Sells always pass position limits
        if signal.action == "sell":
            return True

        # Check max quantity per order
        if signal.quantity > self._config.max_quantity_per_order:
            return False

        # Get current price
        price = await self._get_current_price(signal.symbol)
        position_value = Decimal(str(signal.quantity)) * price

        # Check max position value
        if position_value > self._config.max_position_value:
            return False

        # Check max position as % of portfolio
        account = await self._portfolio.get_account(self._config.account_id)
        position_pct = (position_value / account.total_equity) * 100

        if position_pct > self._config.max_position_pct:
            return False

        return True

    async def _check_portfolio_limits(self, signal: Signal) -> bool:
        """Check portfolio-level limits."""
        account = await self._portfolio.get_account(self._config.account_id)
        if not account:
            return False

        positions = await self._portfolio.get_positions(self._config.account_id)

        # Check max positions (only for new positions, only for buys)
        if signal.action == "buy":
            existing = await self._portfolio.get_position(
                self._config.account_id, signal.symbol, signal.strategy_id
            )
            if not existing and len(positions) >= self._config.max_positions:
                return False

        # Calculate exposure
        total_exposure = sum(p.market_value for p in positions)
        price = await self._get_current_price(signal.symbol)
        new_exposure = (
            Decimal(str(signal.quantity)) * price if signal.action == "buy" else Decimal("0")
        )
        exposure_pct = (total_exposure + new_exposure) / account.total_equity * 100

        if exposure_pct > self._config.max_exposure_pct:
            return False

        # Check buying power (only for buys)
        if signal.action == "buy":
            required = Decimal(str(signal.quantity)) * price
            if required > account.buying_power:
                return False

        return True

    async def evaluate(self, signal: Signal) -> RiskResult:
        """Run all risk checks on a signal."""
        # Kill switch check
        if self._killed:
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason=f"Kill switch active: {self._kill_reason}",
                checks_failed=["kill_switch"],
            )

        # Strategy pause check
        if signal.strategy_id in self._paused_strategies:
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason=f"Strategy {signal.strategy_id} is paused",
                checks_failed=["strategy_paused"],
            )

        # Symbol allowed check
        if not self._check_symbol_allowed(signal):
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason="symbol_allowed",
                checks_failed=["symbol_allowed"],
            )

        # Position limits check
        if not await self._check_position_limits(signal):
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason="position_limits",
                checks_failed=["position_limits"],
            )

        # Portfolio limits check
        if not await self._check_portfolio_limits(signal):
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason="portfolio_limits",
                checks_failed=["portfolio_limits"],
            )

        # Placeholder for remaining checks (implemented in later tasks)
        return RiskResult(
            approved=True,
            signal=signal,
            checks_passed=[
                "kill_switch",
                "strategy_paused",
                "symbol_allowed",
                "position_limits",
                "portfolio_limits",
            ],
        )

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol. Placeholder for market data integration."""
        # TODO: Integrate with market data service
        return Decimal("100")
