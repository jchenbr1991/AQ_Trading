"""Tests for GreeksGate pre-order limit checking.

Tests cover V2 Pre-order Greeks Check (Section 2):
- GreeksGate.check_order returns APPROVED when within limits
- GreeksGate.check_order returns HARD_BREACH when exceeding limits
- GreeksGate handles DATA_UNAVAILABLE (fail-closed)
- GreeksGate handles DATA_STALE (fail-closed)
- Multi-leg order impact calculation
- Fail-open mode option
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.greeks.v2_models import (
    GreeksCheckConfig,
    OrderIntent,
    OrderLeg,
)


def _make_order_intent(
    account_id: str = "acc_001",
    strategy_id: str | None = None,
    legs: list[OrderLeg] | None = None,
) -> OrderIntent:
    """Factory function to create OrderIntent for testing."""
    if legs is None:
        legs = [
            OrderLeg(
                symbol="AAPL240119C00150000",
                side="buy",
                quantity=10,
                contract_type="call",
                strike=Decimal("150"),
                expiry=None,
                multiplier=100,
            )
        ]
    return OrderIntent(
        account_id=account_id,
        strategy_id=strategy_id,
        legs=legs,
    )


def _make_aggregated_greeks_mock(
    dollar_delta: Decimal = Decimal("50000"),
    gamma_dollar: Decimal = Decimal("2000"),
    vega_per_1pct: Decimal = Decimal("10000"),
    theta_per_day: Decimal = Decimal("-2000"),
    as_of_ts: datetime | None = None,
):
    """Create a mock AggregatedGreeks for testing."""
    from src.greeks.models import AggregatedGreeks

    return AggregatedGreeks(
        scope="ACCOUNT",
        scope_id="acc_001",
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=Decimal("100"),
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        valid_legs_count=5,
        total_legs_count=5,
        valid_notional=Decimal("100000"),
        total_notional=Decimal("100000"),
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
        as_of_ts_min=as_of_ts or datetime.now(timezone.utc),
    )


class TestGreeksGateCheckOrder:
    """Tests for GreeksGate.check_order method."""

    @pytest.mark.asyncio
    async def test_returns_approved_when_within_limits(self):
        """Order within limits should be approved."""
        from src.greeks.greeks_gate import GreeksGate

        # Setup: current Greeks at 50% of limits
        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(
            dollar_delta=Decimal("50000"),  # 25% of 200k limit
            gamma_dollar=Decimal("2000"),  # 20% of 10k limit
        )

        mock_calculator = MagicMock()
        # Order impact: +10000 delta, +500 gamma
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("10000"),
                "gamma_dollar": Decimal("500"),
                "vega_per_1pct": Decimal("1000"),
                "theta_per_day": Decimal("-100"),
            }
        )

        config = GreeksCheckConfig(
            hard_limits={
                "dollar_delta": Decimal("200000"),
                "gamma_dollar": Decimal("10000"),
                "vega_per_1pct": Decimal("40000"),
                "theta_per_day": Decimal("6000"),
            }
        )

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is True
        assert result.reason_code == "APPROVED"
        assert result.details is not None
        assert len(result.details.breach_dims) == 0

    @pytest.mark.asyncio
    async def test_returns_hard_breach_when_exceeds_delta_limit(self):
        """Order exceeding delta limit should be blocked."""
        from src.greeks.greeks_gate import GreeksGate

        # Setup: current delta at 180k, order adds 50k = 230k > 200k limit
        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(
            dollar_delta=Decimal("180000"),
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("50000"),
                "gamma_dollar": Decimal("500"),
                "vega_per_1pct": Decimal("1000"),
                "theta_per_day": Decimal("-100"),
            }
        )

        config = GreeksCheckConfig(hard_limits={"dollar_delta": Decimal("200000")})

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is False
        assert result.reason_code == "HARD_BREACH"
        assert result.details is not None
        assert "dollar_delta" in result.details.breach_dims

    @pytest.mark.asyncio
    async def test_returns_data_unavailable_when_no_greeks(self):
        """Missing Greeks data should block order (fail-closed)."""
        from src.greeks.greeks_gate import GreeksGate

        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = None

        mock_calculator = MagicMock()

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is False
        assert result.reason_code == "DATA_UNAVAILABLE"
        assert result.details is None

    @pytest.mark.asyncio
    async def test_returns_data_stale_when_greeks_too_old(self):
        """Stale Greeks data should block order (fail-closed)."""
        from datetime import timedelta

        from src.greeks.greeks_gate import GreeksGate

        # Setup: Greeks from 120 seconds ago, limit is 60 seconds
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=120)
        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(as_of_ts=old_ts)

        mock_calculator = MagicMock()

        config = GreeksCheckConfig(max_staleness_seconds=60)

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is False
        assert result.reason_code == "DATA_STALE"
        assert result.details is None

    @pytest.mark.asyncio
    async def test_uses_abs_for_limit_comparison(self):
        """Limits should be compared using absolute values."""
        from src.greeks.greeks_gate import GreeksGate

        # Setup: current delta is -180k, order adds -50k = -230k
        # abs(-230k) = 230k > 200k limit
        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(
            dollar_delta=Decimal("-180000"),
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("-50000"),
                "gamma_dollar": Decimal("0"),
                "vega_per_1pct": Decimal("0"),
                "theta_per_day": Decimal("0"),
            }
        )

        config = GreeksCheckConfig(hard_limits={"dollar_delta": Decimal("200000")})

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is False
        assert result.reason_code == "HARD_BREACH"
        assert "dollar_delta" in result.details.breach_dims

    @pytest.mark.asyncio
    async def test_fail_open_mode_allows_when_data_unavailable(self):
        """Fail-open mode should allow orders when data unavailable."""
        from src.greeks.greeks_gate import GreeksGate

        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = None

        mock_calculator = MagicMock()

        config = GreeksCheckConfig(fail_mode="open")

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is True
        assert result.reason_code == "APPROVED"

    @pytest.mark.asyncio
    async def test_multiple_breach_dims_returned(self):
        """Multiple breaching dimensions should all be reported."""
        from src.greeks.greeks_gate import GreeksGate

        # Setup: both delta and gamma will breach
        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(
            dollar_delta=Decimal("180000"),
            gamma_dollar=Decimal("9000"),
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("50000"),  # 230k > 200k
                "gamma_dollar": Decimal("2000"),  # 11k > 10k
                "vega_per_1pct": Decimal("0"),
                "theta_per_day": Decimal("0"),
            }
        )

        config = GreeksCheckConfig(
            hard_limits={
                "dollar_delta": Decimal("200000"),
                "gamma_dollar": Decimal("10000"),
            }
        )

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.ok is False
        assert result.reason_code == "HARD_BREACH"
        assert "dollar_delta" in result.details.breach_dims
        assert "gamma_dollar" in result.details.breach_dims

    @pytest.mark.asyncio
    async def test_details_contain_current_impact_projected(self):
        """Result details should contain current, impact, and projected values."""
        from src.greeks.greeks_gate import GreeksGate

        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock(
            dollar_delta=Decimal("50000"),
            gamma_dollar=Decimal("2000"),
            vega_per_1pct=Decimal("10000"),
            theta_per_day=Decimal("-2000"),
        )

        mock_calculator = MagicMock()
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("10000"),
                "gamma_dollar": Decimal("500"),
                "vega_per_1pct": Decimal("1000"),
                "theta_per_day": Decimal("-100"),
            }
        )

        config = GreeksCheckConfig()

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
            config=config,
        )

        order = _make_order_intent()
        result = await gate.check_order(order)

        assert result.details is not None
        # Check current values
        assert result.details.current["dollar_delta"] == Decimal("50000")
        # Check impact values
        assert result.details.impact["dollar_delta"] == Decimal("10000")
        # Check projected = current + impact
        assert result.details.projected["dollar_delta"] == Decimal("60000")


class TestGreeksGateMultiLeg:
    """Tests for multi-leg order handling."""

    @pytest.mark.asyncio
    async def test_multi_leg_order_aggregates_impact(self):
        """Multi-leg orders should aggregate impact from all legs."""
        from src.greeks.greeks_gate import GreeksGate

        mock_monitor = MagicMock()
        mock_monitor.get_current_greeks.return_value = _make_aggregated_greeks_mock()

        mock_calculator = MagicMock()
        # Returns aggregated impact for all legs
        mock_calculator.calculate_order_impact = AsyncMock(
            return_value={
                "dollar_delta": Decimal("5000"),  # Net from spread
                "gamma_dollar": Decimal("100"),
                "vega_per_1pct": Decimal("500"),
                "theta_per_day": Decimal("-50"),
            }
        )

        gate = GreeksGate(
            greeks_monitor=mock_monitor,
            greeks_calculator=mock_calculator,
        )

        # Bull call spread: buy lower strike, sell higher strike
        legs = [
            OrderLeg(
                symbol="AAPL240119C00150000",
                side="buy",
                quantity=10,
                contract_type="call",
                strike=Decimal("150"),
            ),
            OrderLeg(
                symbol="AAPL240119C00160000",
                side="sell",
                quantity=10,
                contract_type="call",
                strike=Decimal("160"),
            ),
        ]
        order = _make_order_intent(legs=legs)

        result = await gate.check_order(order)

        # Verify calculator was called with the order
        mock_calculator.calculate_order_impact.assert_called_once()
        call_args = mock_calculator.calculate_order_impact.call_args
        assert len(call_args[0][0].legs) == 2

        assert result.ok is True
