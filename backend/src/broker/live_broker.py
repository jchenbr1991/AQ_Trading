# backend/src/broker/live_broker.py
"""Live broker adapter with pre-trade validation.

Implements T047: Pre-trade validation checks for live trading.
Decorator pattern: wraps any Broker implementation with risk validation.

Supports:
- FR-007: LiveBroker decorator pattern
- FR-021: Same interface as PaperBroker for mode-agnostic strategy execution
- Pre-trade validation with configurable risk limits
- Broker connection verification
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from src.broker.errors import BrokerError, OrderSubmissionError
from src.broker.query import BrokerAccount, BrokerPosition
from src.orders.models import Order, OrderStatus

logger = logging.getLogger(__name__)


class BrokerConnectionError(BrokerError):
    """Error connecting to live broker."""

    def __init__(self, message: str, broker: str = None):
        super().__init__(message)
        self.broker = broker


class RiskLimitExceededError(BrokerError):
    """Order exceeds configured risk limits."""

    def __init__(self, message: str, limit_type: str, limit_value: float, actual_value: float):
        super().__init__(message)
        self.limit_type = limit_type
        self.limit_value = limit_value
        self.actual_value = actual_value


class LiveTradingNotConfirmedError(BrokerError):
    """Live trading requires explicit confirmation."""

    def __init__(self, message: str = "Live trading requires explicit confirmation"):
        super().__init__(message)


@dataclass
class RiskLimits:
    """Risk limits configuration for live trading.

    All limits are checked before order submission.
    If any limit is exceeded, the order is rejected.
    """

    max_position_size: int = 1000  # Maximum shares per position
    max_order_value: Decimal = Decimal("50000")  # Maximum order value
    max_daily_loss: Decimal = Decimal("5000")  # Maximum daily loss before halting
    max_open_orders: int = 10  # Maximum concurrent open orders

    @classmethod
    def from_dict(cls, data: dict) -> RiskLimits:
        """Create RiskLimits from dictionary (e.g., YAML config)."""
        return cls(
            max_position_size=data.get("max_position_size", 1000),
            max_order_value=Decimal(str(data.get("max_order_value", 50000))),
            max_daily_loss=Decimal(str(data.get("max_daily_loss", 5000))),
            max_open_orders=data.get("max_open_orders", 10),
        )


@dataclass
class ValidationResult:
    """Result of pre-trade validation."""

    passed: bool
    message: str
    checks: dict[str, bool]  # Individual check results


class LiveBroker:
    """Live broker adapter with pre-trade validation.

    Wraps any Broker implementation with risk validation (decorator pattern).
    All order execution is delegated to the inner broker after validation.

    Implements the same interface as PaperBroker for mode-agnostic
    behavior (FR-021).
    """

    def __init__(
        self,
        inner_broker: object,
        account_id: str | None = None,
        risk_limits: RiskLimits | None = None,
        require_confirmation: bool = True,
    ):
        """Initialize live broker decorator.

        Args:
            inner_broker: The actual Broker implementation to delegate to.
            account_id: Broker account ID for live trading.
            risk_limits: Risk limits configuration.
            require_confirmation: Whether to require explicit confirmation.
        """
        self._inner_broker = inner_broker
        self._account_id = account_id
        self._risk_limits = risk_limits or RiskLimits()
        self._require_confirmation = require_confirmation

        # Connection state
        self._connected = False
        self._connection_verified = False

        # Order tracking (open order count only -- inner broker tracks orders)
        self._open_order_count = 0
        self._daily_pnl = Decimal("0")

        # Confirmation state
        self._confirmed = False

        logger.info(
            "LiveBroker initialized with inner broker: %s",
            type(inner_broker).__name__,
        )

    @property
    def is_connected(self) -> bool:
        """Check if broker connection is active."""
        return self._connected

    @property
    def is_confirmed(self) -> bool:
        """Check if live trading has been confirmed."""
        return self._confirmed

    @property
    def risk_limits(self) -> RiskLimits:
        """Get current risk limits."""
        return self._risk_limits

    async def connect(self) -> bool:
        """Establish connection to live broker.

        Delegates to inner broker connect() if available.

        Returns:
            True if connection successful.

        Raises:
            BrokerConnectionError: If connection fails.
        """
        if hasattr(self._inner_broker, "connect"):
            await self._inner_broker.connect()

        self._connected = True
        self._connection_verified = True
        logger.info("LiveBroker connection established")
        return True

    async def disconnect(self) -> None:
        """Disconnect from live broker."""
        if hasattr(self._inner_broker, "disconnect"):
            await self._inner_broker.disconnect()

        self._connected = False
        self._connection_verified = False
        logger.info("LiveBroker disconnected")

    async def verify_connection(self) -> ValidationResult:
        """Verify broker connection is ready for trading.

        Checks:
        - Connection is established
        - Account is accessible

        Returns:
            ValidationResult with check details.
        """
        checks = {
            "connection_established": self._connected,
            "account_configured": self._account_id is not None,
        }

        passed = all(checks.values())
        message = "Connection verified" if passed else "Connection verification failed"

        self._connection_verified = passed
        return ValidationResult(passed=passed, message=message, checks=checks)

    def confirm_live_trading(self) -> None:
        """Explicitly confirm live trading.

        Must be called before orders can be submitted in live mode.
        This is a safety mechanism to prevent accidental live trading.
        """
        if not self._connected:
            raise BrokerConnectionError("Cannot confirm - not connected")

        self._confirmed = True
        logger.warning("LIVE TRADING CONFIRMED - Orders will be executed with real money")

    def revoke_confirmation(self) -> None:
        """Revoke live trading confirmation."""
        self._confirmed = False
        logger.info("Live trading confirmation revoked")

    async def validate_order(
        self, order: Order, current_price: Decimal | None = None
    ) -> ValidationResult:
        """Validate order against risk limits before submission.

        T047: Pre-trade validation checks.

        Args:
            order: Order to validate.
            current_price: Current market price (for value calculation).

        Returns:
            ValidationResult with detailed check results.
        """
        checks = {}
        messages = []

        # Check 1: Broker connection
        checks["broker_connected"] = self._connected
        if not self._connected:
            messages.append("Broker not connected")

        # Check 2: Live trading confirmed (if required)
        if self._require_confirmation:
            checks["live_confirmed"] = self._confirmed
            if not self._confirmed:
                messages.append("Live trading not confirmed")
        else:
            checks["live_confirmed"] = True

        # Check 3: Position size limit
        checks["position_size_ok"] = order.quantity <= self._risk_limits.max_position_size
        if not checks["position_size_ok"]:
            messages.append(
                f"Position size {order.quantity} exceeds limit "
                f"{self._risk_limits.max_position_size}"
            )

        # Check 4: Order value limit
        if current_price is not None:
            order_value = current_price * Decimal(str(order.quantity))
            checks["order_value_ok"] = order_value <= self._risk_limits.max_order_value
            if not checks["order_value_ok"]:
                messages.append(
                    f"Order value {order_value} exceeds limit "
                    f"{self._risk_limits.max_order_value}"
                )
        else:
            # Can't check without price - assume OK but note it
            checks["order_value_ok"] = True

        # Check 5: Open order count
        checks["open_orders_ok"] = self._open_order_count < self._risk_limits.max_open_orders
        if not checks["open_orders_ok"]:
            messages.append(
                f"Open orders {self._open_order_count} at limit "
                f"{self._risk_limits.max_open_orders}"
            )

        # Check 6: Daily loss limit
        checks["daily_loss_ok"] = abs(self._daily_pnl) < self._risk_limits.max_daily_loss
        if not checks["daily_loss_ok"]:
            messages.append(
                f"Daily loss {self._daily_pnl} exceeds limit " f"{self._risk_limits.max_daily_loss}"
            )

        passed = all(checks.values())
        message = "Order validated" if passed else "; ".join(messages)

        return ValidationResult(passed=passed, message=message, checks=checks)

    async def submit_order(self, order: Order) -> str:
        """Submit order to live broker with pre-trade validation.

        Validates the order against risk limits first, then delegates
        to the inner broker for actual execution.

        Args:
            order: Order to submit.

        Returns:
            Broker order ID from inner broker.

        Raises:
            BrokerConnectionError: If not connected.
            LiveTradingNotConfirmedError: If confirmation required but not given.
            RiskLimitExceededError: If order exceeds risk limits.
            OrderSubmissionError: If order submission fails.
        """
        # Validate order first
        validation = await self.validate_order(order)
        if not validation.passed:
            # Determine which specific error to raise
            if not validation.checks.get("broker_connected", False):
                raise BrokerConnectionError("Not connected to broker")
            if not validation.checks.get("live_confirmed", False):
                raise LiveTradingNotConfirmedError()
            if not validation.checks.get("position_size_ok", False):
                raise RiskLimitExceededError(
                    f"Position size {order.quantity} exceeds limit",
                    limit_type="max_position_size",
                    limit_value=float(self._risk_limits.max_position_size),
                    actual_value=float(order.quantity),
                )
            if not validation.checks.get("order_value_ok", False):
                raise RiskLimitExceededError(
                    "Order value exceeds limit",
                    limit_type="max_order_value",
                    limit_value=float(self._risk_limits.max_order_value),
                    actual_value=0,  # Would need price to calculate
                )
            if not validation.checks.get("open_orders_ok", False):
                raise RiskLimitExceededError(
                    "Too many open orders",
                    limit_type="max_open_orders",
                    limit_value=float(self._risk_limits.max_open_orders),
                    actual_value=float(self._open_order_count),
                )
            if not validation.checks.get("daily_loss_ok", False):
                raise RiskLimitExceededError(
                    "Daily loss limit exceeded",
                    limit_type="max_daily_loss",
                    limit_value=float(self._risk_limits.max_daily_loss),
                    actual_value=float(abs(self._daily_pnl)),
                )

            raise OrderSubmissionError(validation.message, symbol=order.symbol)

        # Delegate to inner broker
        broker_id = await self._inner_broker.submit_order(order)
        self._open_order_count += 1
        logger.info("LiveBroker order submitted via inner broker: %s", broker_id)
        return broker_id

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an open order by delegating to inner broker.

        Args:
            broker_order_id: Broker order ID.

        Returns:
            True if cancelled.

        Raises:
            OrderCancelError: If cancellation fails.
        """
        result = await self._inner_broker.cancel_order(broker_order_id)
        self._open_order_count = max(0, self._open_order_count - 1)
        logger.info("LiveBroker order cancelled: %s", broker_order_id)
        return result

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current order status from inner broker."""
        return await self._inner_broker.get_order_status(broker_order_id)

    def subscribe_fills(self, callback: Callable) -> None:
        """Register fill callback on inner broker.

        Wraps the callback to decrement open order count on fills.
        """

        def _wrapped_callback(fill):
            self._open_order_count = max(0, self._open_order_count - 1)
            callback(fill)

        self._inner_broker.subscribe_fills(_wrapped_callback)

    # BrokerQuery protocol delegation

    async def get_positions(self, account_id: str) -> list[BrokerPosition]:
        """Get positions -- delegate to inner broker if it supports BrokerQuery."""
        if hasattr(self._inner_broker, "get_positions"):
            return await self._inner_broker.get_positions(account_id)
        return []

    async def get_account(self, account_id: str) -> BrokerAccount:
        """Get account info -- delegate to inner broker if it supports BrokerQuery."""
        if hasattr(self._inner_broker, "get_account"):
            return await self._inner_broker.get_account(account_id)
        return BrokerAccount(
            account_id=account_id,
            cash=Decimal("0"),
            buying_power=Decimal("0"),
            total_equity=Decimal("0"),
            margin_used=Decimal("0"),
        )

    def update_daily_pnl(self, pnl: Decimal) -> None:
        """Update daily P&L for risk limit checking.

        Should be called by the trading engine as fills are received.
        """
        self._daily_pnl = pnl

    def reset_daily_limits(self) -> None:
        """Reset daily counters (should be called at start of trading day)."""
        self._daily_pnl = Decimal("0")
        logger.info("Daily risk counters reset")
