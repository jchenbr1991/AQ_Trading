import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from src.db.redis_keys import AgentKeys
from src.greeks.v2_models import OrderIntent, OrderLeg
from src.risk.models import RiskConfig, RiskResult
from src.strategies.signals import Signal

if TYPE_CHECKING:
    from src.greeks.greeks_gate import GreeksGate
    from src.greeks.v2_models import GreeksCheckResult

logger = logging.getLogger(__name__)


class PortfolioProtocol(Protocol):
    """Protocol for portfolio manager dependency."""

    async def get_account(self, account_id: str): ...
    async def get_positions(self, account_id: str): ...
    async def get_position(self, account_id: str, symbol: str, strategy_id: str): ...


class RedisClientProtocol(Protocol):
    """Protocol for Redis client dependency."""

    async def get(self, key: str) -> str | None: ...


class RiskManager:
    """Validates trading signals against risk limits."""

    # Default risk bias when Redis is unavailable or key is missing
    DEFAULT_RISK_BIAS = 1.0

    def __init__(
        self,
        config: RiskConfig,
        portfolio: PortfolioProtocol,
        greeks_gate: "GreeksGate | None" = None,
        redis: "RedisClientProtocol | None" = None,
    ):
        self._config = config
        self._portfolio = portfolio
        self._greeks_gate = greeks_gate
        self._redis = redis
        self._killed = False
        self._kill_reason: str | None = None
        self._paused_strategies: set[str] = set()
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: Decimal = Decimal("0")
        self._last_greeks_check: GreeksCheckResult | None = None

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

    # P&L tracking
    def update_daily_pnl(self, pnl_change: Decimal) -> None:
        """Update daily P&L with a change."""
        self._daily_pnl += pnl_change

    def reset_daily_stats(self) -> None:
        """Reset daily statistics. Called at start of trading day."""
        self._daily_pnl = Decimal("0")

    async def get_risk_bias(self) -> float:
        """Get the current risk bias from Redis.

        Risk bias is a multiplier applied to position limits. A value of 1.0 means
        no adjustment, <1.0 reduces limits, >1.0 increases limits.

        Implements graceful degradation per FR-021:
        - If Redis is unavailable, returns default bias (1.0)
        - If key is missing, returns default bias (1.0)
        - Trading continues normally when agent subsystem fails

        Returns:
            Risk bias multiplier (float). Default is 1.0 if unavailable.
        """
        if self._redis is None:
            logger.debug("Redis not configured, using default risk bias")
            return self.DEFAULT_RISK_BIAS

        try:
            value = await self._redis.get(AgentKeys.RISK_BIAS)
            if value is None:
                logger.debug("Risk bias key not found in Redis, using default")
                return self.DEFAULT_RISK_BIAS
            bias = float(value)
            logger.debug(f"Retrieved risk bias from Redis: {bias}")
            return bias
        except (ConnectionError, TimeoutError) as e:
            logger.warning(f"Redis unavailable for risk bias, using default: {e}")
            return self.DEFAULT_RISK_BIAS
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid risk bias value in Redis, using default: {e}")
            return self.DEFAULT_RISK_BIAS
        except Exception as e:
            logger.warning(f"Unexpected error reading risk bias, using default: {e}")
            return self.DEFAULT_RISK_BIAS

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
        """Check position-level limits.

        Risk bias from Redis is applied to position limits:
        - effective_max_position_value = max_position_value * risk_bias
        - effective_max_quantity = max_quantity_per_order * risk_bias

        This allows the RiskController agent to dynamically adjust risk limits
        based on market conditions (SC-014).
        """
        # Sells always pass position limits
        if signal.action == "sell":
            return True

        # Get risk bias for limit adjustments
        risk_bias = await self.get_risk_bias()
        bias_decimal = Decimal(str(risk_bias))

        # Apply bias to quantity limit
        effective_max_quantity = int(self._config.max_quantity_per_order * risk_bias)
        if signal.quantity > effective_max_quantity:
            return False

        # Get current price
        price = await self._get_current_price(signal.symbol)
        position_value = Decimal(str(signal.quantity)) * price

        # Apply bias to max position value
        effective_max_position_value = self._config.max_position_value * bias_decimal
        if position_value > effective_max_position_value:
            return False

        # Check max position as % of portfolio (also apply bias)
        account = await self._portfolio.get_account(self._config.account_id)
        position_pct = (position_value / account.total_equity) * 100
        effective_max_position_pct = self._config.max_position_pct * bias_decimal

        if position_pct > effective_max_position_pct:
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

    async def _check_loss_limits(self, signal: Signal) -> bool:
        """Check loss limits (daily loss, drawdown)."""
        # Check daily loss limit
        if self._daily_pnl < -self._config.daily_loss_limit:
            self.activate_kill_switch("Daily loss limit exceeded")
            return False

        # Check drawdown
        account = await self._portfolio.get_account(self._config.account_id)

        # Update peak equity if new high
        if account.total_equity > self._peak_equity:
            self._peak_equity = account.total_equity

        # Calculate drawdown (handle initial case)
        if self._peak_equity > 0:
            drawdown_pct = (self._peak_equity - account.total_equity) / self._peak_equity * 100
            if drawdown_pct > self._config.max_drawdown_pct:
                self.activate_kill_switch(f"Drawdown {drawdown_pct:.1f}% exceeded limit")
                return False

        return True

    async def _check_greeks_limits(self, signal: Signal) -> bool:
        """Check Greeks limits via GreeksGate.

        V2 Feature: Pre-order Greeks Check

        Args:
            signal: The trading signal to check.

        Returns:
            True if within limits or no gate configured, False if breach.
        """
        # Skip if no Greeks gate configured
        if self._greeks_gate is None:
            return True

        # Convert signal to OrderIntent
        order = OrderIntent(
            account_id=self._config.account_id,
            strategy_id=signal.strategy_id,
            legs=[
                OrderLeg(
                    symbol=signal.symbol,
                    side=signal.action,
                    quantity=signal.quantity,
                    contract_type="call",  # TODO: Infer from symbol
                )
            ],
        )

        # Check via gate
        result = await self._greeks_gate.check_order(order)
        self._last_greeks_check = result

        return result.ok

    async def evaluate(self, signal: Signal) -> RiskResult:
        """Run all risk checks on a signal."""
        # Reset Greeks check result
        self._last_greeks_check = None

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

        # Loss limits check
        if not await self._check_loss_limits(signal):
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason="loss_limits",
                checks_failed=["loss_limits"],
            )

        # Greeks limits check (V2)
        if not await self._check_greeks_limits(signal):
            return RiskResult(
                approved=False,
                signal=signal,
                rejection_reason="greeks_limits",
                checks_failed=["greeks_limits"],
                greeks_check_result=self._last_greeks_check,
            )

        return RiskResult(
            approved=True,
            signal=signal,
            checks_passed=[
                "kill_switch",
                "strategy_paused",
                "symbol_allowed",
                "position_limits",
                "portfolio_limits",
                "loss_limits",
                "greeks_limits",
            ],
            greeks_check_result=self._last_greeks_check,
        )

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol. Placeholder for market data integration."""
        # TODO: Integrate with market data service
        return Decimal("100")
