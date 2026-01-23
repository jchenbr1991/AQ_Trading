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

        # Placeholder for remaining checks (implemented in later tasks)
        return RiskResult(
            approved=True, signal=signal, checks_passed=["kill_switch", "strategy_paused"]
        )

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol. Placeholder for market data integration."""
        # TODO: Integrate with market data service
        return Decimal("100")
