# backend/tests/broker/test_live_broker.py
"""Tests for LiveBroker decorator pattern (FR-007).

LiveBroker wraps an inner Broker implementation with pre-trade risk
validation. These tests verify delegation, validation, and error handling.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.broker.base import Broker
from src.broker.live_broker import (
    BrokerConnectionError,
    LiveBroker,
    LiveTradingNotConfirmedError,
    RiskLimitExceededError,
    RiskLimits,
)
from src.broker.query import BrokerAccount
from src.orders.models import Order, OrderStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_order(**overrides) -> Order:
    """Create a test order with sensible defaults."""
    defaults = {
        "order_id": "ord-001",
        "broker_order_id": None,
        "strategy_id": "test-strat",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 100,
        "order_type": "market",
        "limit_price": None,
        "status": OrderStatus.PENDING,
    }
    defaults.update(overrides)
    return Order(**defaults)


def _make_inner_broker() -> AsyncMock:
    """Create a mock that satisfies the Broker protocol."""
    mock = AsyncMock(spec=Broker)
    mock.submit_order.return_value = "INNER-000001"
    mock.cancel_order.return_value = True
    mock.get_order_status.return_value = OrderStatus.SUBMITTED
    mock.subscribe_fills = MagicMock()
    return mock


def _connected_confirmed_broker(
    inner: AsyncMock | None = None,
    risk_limits: RiskLimits | None = None,
) -> LiveBroker:
    """Return a LiveBroker that is connected and confirmed for trading."""
    inner = inner or _make_inner_broker()
    lb = LiveBroker(
        inner_broker=inner,
        risk_limits=risk_limits,
    )
    # Manually set internal state so we don't need async connect
    lb._connected = True
    lb._confirmed = True
    return lb


# ---------------------------------------------------------------------------
# T003: Constructor
# ---------------------------------------------------------------------------


class TestLiveBrokerConstructor:
    """LiveBroker accepts inner_broker: Broker parameter."""

    def test_accepts_inner_broker(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        assert lb._inner_broker is inner

    def test_default_risk_limits(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        assert lb.risk_limits.max_position_size == 1000

    def test_custom_risk_limits(self):
        inner = _make_inner_broker()
        limits = RiskLimits(max_position_size=500)
        lb = LiveBroker(inner_broker=inner, risk_limits=limits)
        assert lb.risk_limits.max_position_size == 500

    def test_not_connected_initially(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        assert lb.is_connected is False

    def test_not_confirmed_initially(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        assert lb.is_confirmed is False


# ---------------------------------------------------------------------------
# T003: submit_order delegation
# ---------------------------------------------------------------------------


class TestSubmitOrderDelegation:
    """submit_order delegates to inner broker AFTER risk validation passes."""

    async def test_delegates_to_inner_broker(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        order = _make_order()

        broker_id = await lb.submit_order(order)

        inner.submit_order.assert_awaited_once_with(order)
        assert broker_id == "INNER-000001"

    async def test_returns_inner_broker_order_id(self):
        inner = _make_inner_broker()
        inner.submit_order.return_value = "TIGER-12345"
        lb = _connected_confirmed_broker(inner)

        broker_id = await lb.submit_order(_make_order())

        assert broker_id == "TIGER-12345"

    async def test_does_not_delegate_when_validation_fails(self):
        """If risk validation fails, inner broker is never called."""
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        # Not connected, not confirmed -- validation will fail
        order = _make_order()

        with pytest.raises(BrokerConnectionError):
            await lb.submit_order(order)

        inner.submit_order.assert_not_awaited()

    async def test_increments_open_order_count(self):
        lb = _connected_confirmed_broker()
        assert lb._open_order_count == 0

        await lb.submit_order(_make_order())
        assert lb._open_order_count == 1


# ---------------------------------------------------------------------------
# T003: cancel_order delegation
# ---------------------------------------------------------------------------


class TestCancelOrderDelegation:
    """cancel_order delegates to inner broker."""

    async def test_delegates_to_inner_broker(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)

        result = await lb.cancel_order("INNER-000001")

        inner.cancel_order.assert_awaited_once_with("INNER-000001")
        assert result is True

    async def test_decrements_open_order_count(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        lb._open_order_count = 3

        await lb.cancel_order("INNER-000001")

        assert lb._open_order_count == 2

    async def test_open_order_count_does_not_go_negative(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        lb._open_order_count = 0

        await lb.cancel_order("INNER-000001")

        assert lb._open_order_count == 0


# ---------------------------------------------------------------------------
# T003: get_order_status delegation
# ---------------------------------------------------------------------------


class TestGetOrderStatusDelegation:
    """get_order_status delegates to inner broker."""

    async def test_delegates_to_inner_broker(self):
        inner = _make_inner_broker()
        inner.get_order_status.return_value = OrderStatus.FILLED
        lb = _connected_confirmed_broker(inner)

        status = await lb.get_order_status("INNER-000001")

        inner.get_order_status.assert_awaited_once_with("INNER-000001")
        assert status == OrderStatus.FILLED

    async def test_returns_various_statuses(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)

        for expected in [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILL,
            OrderStatus.CANCELLED,
        ]:
            inner.get_order_status.return_value = expected
            status = await lb.get_order_status("INNER-000001")
            assert status == expected


# ---------------------------------------------------------------------------
# T003: subscribe_fills delegation
# ---------------------------------------------------------------------------


class TestSubscribeFillsDelegation:
    """subscribe_fills delegates to inner broker with fill tracking."""

    def test_delegates_to_inner_broker(self):
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        callback = MagicMock()

        lb.subscribe_fills(callback)

        inner.subscribe_fills.assert_called_once()

    def test_fill_decrements_open_order_count(self):
        """When a fill comes through, open_order_count should decrement."""
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        lb._open_order_count = 3
        user_callback = MagicMock()

        lb.subscribe_fills(user_callback)

        # Extract the wrapped callback that was registered on inner broker
        wrapped = inner.subscribe_fills.call_args[0][0]

        # Simulate a fill
        fake_fill = MagicMock()
        wrapped(fake_fill)

        assert lb._open_order_count == 2
        user_callback.assert_called_once_with(fake_fill)

    def test_fill_does_not_decrement_below_zero(self):
        """Open order count should not go negative from fills."""
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)
        lb._open_order_count = 0
        user_callback = MagicMock()

        lb.subscribe_fills(user_callback)
        wrapped = inner.subscribe_fills.call_args[0][0]
        wrapped(MagicMock())

        assert lb._open_order_count == 0


# ---------------------------------------------------------------------------
# T003: Risk validation
# ---------------------------------------------------------------------------


class TestRiskValidation:
    """Risk validation rejects oversized orders and unconfirmed trading."""

    async def test_rejects_when_not_connected(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        # Not connected

        with pytest.raises(BrokerConnectionError):
            await lb.submit_order(_make_order())

    async def test_rejects_when_not_confirmed(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        lb._connected = True  # connected but not confirmed

        with pytest.raises(LiveTradingNotConfirmedError):
            await lb.submit_order(_make_order())

    async def test_rejects_oversized_position(self):
        limits = RiskLimits(max_position_size=50)
        lb = _connected_confirmed_broker(risk_limits=limits)

        with pytest.raises(RiskLimitExceededError) as exc_info:
            await lb.submit_order(_make_order(quantity=100))

        assert exc_info.value.limit_type == "max_position_size"

    async def test_rejects_too_many_open_orders(self):
        limits = RiskLimits(max_open_orders=2)
        lb = _connected_confirmed_broker(risk_limits=limits)
        lb._open_order_count = 2

        with pytest.raises(RiskLimitExceededError) as exc_info:
            await lb.submit_order(_make_order())

        assert exc_info.value.limit_type == "max_open_orders"

    async def test_rejects_when_daily_loss_exceeded(self):
        limits = RiskLimits(max_daily_loss=Decimal("1000"))
        lb = _connected_confirmed_broker(risk_limits=limits)
        lb.update_daily_pnl(Decimal("-1500"))

        with pytest.raises(RiskLimitExceededError) as exc_info:
            await lb.submit_order(_make_order())

        assert exc_info.value.limit_type == "max_daily_loss"

    async def test_allows_order_when_all_checks_pass(self):
        """A valid order should pass all risk checks and succeed."""
        inner = _make_inner_broker()
        lb = _connected_confirmed_broker(inner)

        broker_id = await lb.submit_order(_make_order(quantity=10))

        assert broker_id == "INNER-000001"
        inner.submit_order.assert_awaited_once()

    async def test_skips_confirmation_check_when_not_required(self):
        """When require_confirmation=False, unconfirmed is OK."""
        inner = _make_inner_broker()
        lb = LiveBroker(
            inner_broker=inner,
            require_confirmation=False,
        )
        lb._connected = True
        # Not confirmed, but shouldn't matter

        broker_id = await lb.submit_order(_make_order())
        assert broker_id == "INNER-000001"


# ---------------------------------------------------------------------------
# T003: validate_order
# ---------------------------------------------------------------------------


class TestValidateOrder:
    """Direct validation method tests."""

    async def test_passes_valid_order(self):
        lb = _connected_confirmed_broker()
        result = await lb.validate_order(_make_order())
        assert result.passed is True
        assert result.message == "Order validated"

    async def test_checks_order_value(self):
        limits = RiskLimits(max_order_value=Decimal("1000"))
        lb = _connected_confirmed_broker(risk_limits=limits)

        result = await lb.validate_order(
            _make_order(quantity=100),
            current_price=Decimal("50"),  # 100 * 50 = 5000 > 1000
        )

        assert result.passed is False
        assert result.checks["order_value_ok"] is False


# ---------------------------------------------------------------------------
# T003: connect / disconnect
# ---------------------------------------------------------------------------


class TestConnectDisconnect:
    """connect/disconnect delegate to inner broker when it supports them."""

    async def test_connect_delegates_to_inner(self):
        inner = _make_inner_broker()
        inner.connect = AsyncMock(return_value=True)
        lb = LiveBroker(inner_broker=inner)

        result = await lb.connect()

        assert result is True
        assert lb.is_connected is True
        inner.connect.assert_awaited_once()

    async def test_connect_works_without_inner_connect(self):
        """If inner broker has no connect(), LiveBroker still connects."""
        inner = _make_inner_broker()
        # AsyncMock(spec=Broker) won't have connect
        lb = LiveBroker(inner_broker=inner)

        result = await lb.connect()

        assert result is True
        assert lb.is_connected is True

    async def test_disconnect_delegates_to_inner(self):
        inner = _make_inner_broker()
        inner.disconnect = AsyncMock()
        lb = LiveBroker(inner_broker=inner)
        lb._connected = True

        await lb.disconnect()

        assert lb.is_connected is False
        inner.disconnect.assert_awaited_once()

    async def test_disconnect_works_without_inner_disconnect(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        lb._connected = True

        await lb.disconnect()

        assert lb.is_connected is False


# ---------------------------------------------------------------------------
# T003: confirm_live_trading / revoke
# ---------------------------------------------------------------------------


class TestConfirmation:
    """Confirmation state management."""

    def test_confirm_requires_connection(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)

        with pytest.raises(BrokerConnectionError):
            lb.confirm_live_trading()

    def test_confirm_succeeds_when_connected(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner)
        lb._connected = True

        lb.confirm_live_trading()

        assert lb.is_confirmed is True

    def test_revoke_confirmation(self):
        lb = _connected_confirmed_broker()
        assert lb.is_confirmed is True

        lb.revoke_confirmation()

        assert lb.is_confirmed is False


# ---------------------------------------------------------------------------
# T003: verify_connection
# ---------------------------------------------------------------------------


class TestVerifyConnection:
    """Connection verification."""

    async def test_passes_when_connected_with_account(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner, account_id="ACC001")
        lb._connected = True

        result = await lb.verify_connection()

        assert result.passed is True
        assert result.checks["connection_established"] is True
        assert result.checks["account_configured"] is True

    async def test_fails_when_not_connected(self):
        inner = _make_inner_broker()
        lb = LiveBroker(inner_broker=inner, account_id="ACC001")

        result = await lb.verify_connection()

        assert result.passed is False
        assert result.checks["connection_established"] is False


# ---------------------------------------------------------------------------
# T003: daily limits management
# ---------------------------------------------------------------------------


class TestDailyLimits:
    """Daily P&L and limits management."""

    def test_update_daily_pnl(self):
        lb = _connected_confirmed_broker()
        lb.update_daily_pnl(Decimal("-500"))
        assert lb._daily_pnl == Decimal("-500")

    def test_reset_daily_limits(self):
        lb = _connected_confirmed_broker()
        lb.update_daily_pnl(Decimal("-3000"))
        lb.reset_daily_limits()
        assert lb._daily_pnl == Decimal("0")


# ---------------------------------------------------------------------------
# T003: BrokerQuery delegation (get_positions, get_account)
# ---------------------------------------------------------------------------


class TestBrokerQueryDelegation:
    """get_positions/get_account delegate when inner supports BrokerQuery."""

    async def test_get_positions_delegates(self):
        inner = _make_inner_broker()
        inner.get_positions = AsyncMock(return_value=[])
        lb = _connected_confirmed_broker(inner)

        result = await lb.get_positions("ACC001")

        inner.get_positions.assert_awaited_once_with("ACC001")
        assert result == []

    async def test_get_account_delegates(self):
        inner = _make_inner_broker()
        expected = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("50000"),
            buying_power=Decimal("100000"),
            total_equity=Decimal("50000"),
            margin_used=Decimal("0"),
        )
        inner.get_account = AsyncMock(return_value=expected)
        lb = _connected_confirmed_broker(inner)

        result = await lb.get_account("ACC001")

        inner.get_account.assert_awaited_once_with("ACC001")
        assert result == expected

    async def test_get_positions_fallback_when_not_supported(self):
        """If inner broker doesn't support get_positions, return empty."""
        inner = _make_inner_broker()
        if hasattr(inner, "get_positions"):
            del inner.get_positions
        lb = _connected_confirmed_broker(inner)

        result = await lb.get_positions("ACC001")

        assert result == []

    async def test_get_account_fallback_when_not_supported(self):
        """If inner broker doesn't support get_account, return default."""
        inner = _make_inner_broker()
        if hasattr(inner, "get_account"):
            del inner.get_account
        lb = _connected_confirmed_broker(inner)

        result = await lb.get_account("ACC001")

        assert result.account_id == "ACC001"
        assert result.cash == Decimal("0")


# ---------------------------------------------------------------------------
# T048: Integration — LiveBroker wrapping mock TigerBroker
# ---------------------------------------------------------------------------


class TestLiveBrokerTigerIntegration:
    """LiveBroker wrapping a mock TigerBroker applies risk controls (SC-005)."""

    def _make_mock_tiger(self):
        """Create a mock that mimics TigerBroker interface."""
        mock = AsyncMock()
        mock.submit_order.return_value = "TIGER-001"
        mock.cancel_order.return_value = True
        mock.get_order_status.return_value = OrderStatus.SUBMITTED
        mock.subscribe_fills = MagicMock()
        return mock

    async def test_risk_rejects_oversized_order_before_tiger(self):
        """Oversized order is rejected; TigerBroker never called."""
        tiger = self._make_mock_tiger()
        limits = RiskLimits(max_position_size=50)
        lb = LiveBroker(inner_broker=tiger, risk_limits=limits)
        lb._connected = True
        lb._confirmed = True

        order = _make_order(quantity=100)
        with pytest.raises(RiskLimitExceededError) as exc_info:
            await lb.submit_order(order)

        assert exc_info.value.limit_type == "max_position_size"
        tiger.submit_order.assert_not_awaited()

    async def test_risk_rejects_daily_loss_before_tiger(self):
        """Daily loss limit blocks order; TigerBroker never called."""
        tiger = self._make_mock_tiger()
        limits = RiskLimits(max_daily_loss=Decimal("1000"))
        lb = LiveBroker(inner_broker=tiger, risk_limits=limits)
        lb._connected = True
        lb._confirmed = True
        lb.update_daily_pnl(Decimal("-1500"))

        with pytest.raises(RiskLimitExceededError):
            await lb.submit_order(_make_order())

        tiger.submit_order.assert_not_awaited()

    async def test_valid_order_delegates_to_tiger(self):
        """Valid order passes risk checks and reaches TigerBroker."""
        tiger = self._make_mock_tiger()
        lb = LiveBroker(inner_broker=tiger)
        lb._connected = True
        lb._confirmed = True

        order = _make_order(quantity=10)
        broker_id = await lb.submit_order(order)

        assert broker_id == "TIGER-001"
        tiger.submit_order.assert_awaited_once_with(order)

    async def test_confirmation_required_blocks_tiger(self):
        """Unconfirmed LiveBroker rejects order; TigerBroker never called."""
        tiger = self._make_mock_tiger()
        lb = LiveBroker(inner_broker=tiger, require_confirmation=True)
        lb._connected = True
        # Not confirmed

        with pytest.raises(LiveTradingNotConfirmedError):
            await lb.submit_order(_make_order())

        tiger.submit_order.assert_not_awaited()
