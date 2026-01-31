"""Tests for LimitsStore.

Tests cover V2 PUT /limits (Section 4):
- LimitsStore.get_limits returns current limits
- LimitsStore.set_limits updates limits
- Validation: 0 < warn < crit < hard
- Limits are persisted to cache
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from src.greeks.v2_models import GreeksLimitSet, ThresholdLevels


def _make_limit_set() -> GreeksLimitSet:
    """Factory for valid GreeksLimitSet."""
    return GreeksLimitSet(
        dollar_delta=ThresholdLevels(
            warn=Decimal("100000"),
            crit=Decimal("150000"),
            hard=Decimal("200000"),
        ),
        gamma_dollar=ThresholdLevels(
            warn=Decimal("5000"),
            crit=Decimal("7500"),
            hard=Decimal("10000"),
        ),
        vega_per_1pct=ThresholdLevels(
            warn=Decimal("20000"),
            crit=Decimal("30000"),
            hard=Decimal("40000"),
        ),
        theta_per_day=ThresholdLevels(
            warn=Decimal("3000"),
            crit=Decimal("4500"),
            hard=Decimal("6000"),
        ),
    )


class TestThresholdLevelsValidation:
    """Tests for ThresholdLevels.validate()."""

    def test_valid_levels_pass(self):
        """Valid threshold ordering passes validation."""
        levels = ThresholdLevels(
            warn=Decimal("100"),
            crit=Decimal("150"),
            hard=Decimal("200"),
        )
        errors = levels.validate()
        assert errors == []

    def test_invalid_warn_gt_crit_fails(self):
        """warn > crit fails validation."""
        levels = ThresholdLevels(
            warn=Decimal("200"),  # warn > crit
            crit=Decimal("150"),
            hard=Decimal("300"),
        )
        errors = levels.validate()
        assert len(errors) == 1
        assert "0 < warn < crit < hard" in errors[0]

    def test_invalid_zero_warn_fails(self):
        """warn = 0 fails validation."""
        levels = ThresholdLevels(
            warn=Decimal("0"),
            crit=Decimal("150"),
            hard=Decimal("200"),
        )
        errors = levels.validate()
        assert len(errors) == 1


class TestGreeksLimitSetValidation:
    """Tests for GreeksLimitSet.validate()."""

    def test_valid_limit_set_passes(self):
        """Valid limit set passes validation."""
        limit_set = _make_limit_set()
        errors = limit_set.validate()
        assert errors == []

    def test_reports_all_invalid_fields(self):
        """Reports errors for all invalid fields."""
        limit_set = GreeksLimitSet(
            dollar_delta=ThresholdLevels(
                warn=Decimal("200"),  # Invalid
                crit=Decimal("100"),
                hard=Decimal("300"),
            ),
            gamma_dollar=ThresholdLevels(
                warn=Decimal("0"),  # Invalid
                crit=Decimal("100"),
                hard=Decimal("200"),
            ),
            vega_per_1pct=ThresholdLevels(
                warn=Decimal("100"),
                crit=Decimal("150"),
                hard=Decimal("200"),  # Valid
            ),
            theta_per_day=ThresholdLevels(
                warn=Decimal("100"),
                crit=Decimal("150"),
                hard=Decimal("200"),  # Valid
            ),
        )
        errors = limit_set.validate()
        assert len(errors) == 2
        assert any("dollar_delta" in e for e in errors)
        assert any("gamma_dollar" in e for e in errors)


class TestLimitsStore:
    """Tests for LimitsStore class."""

    @pytest.mark.asyncio
    async def test_get_limits_returns_default_if_not_set(self):
        """get_limits returns default limits if not set."""
        from src.greeks.limits_store import LimitsStore

        store = LimitsStore()
        limits = await store.get_limits("acc_001")

        assert limits is not None
        assert limits.dollar_delta.hard == Decimal("200000")

    @pytest.mark.asyncio
    async def test_set_limits_stores_limits(self):
        """set_limits stores limits for retrieval."""
        from src.greeks.limits_store import LimitsStore

        store = LimitsStore()
        new_limits = _make_limit_set()
        new_limits.dollar_delta.hard = Decimal("250000")

        result = await store.set_limits(
            account_id="acc_001",
            limits=new_limits,
            updated_by="user_123",
        )

        assert result.limits.dollar_delta.hard == Decimal("250000")
        assert result.updated_by == "user_123"

        # Verify retrieval
        retrieved = await store.get_limits("acc_001")
        assert retrieved.dollar_delta.hard == Decimal("250000")

    @pytest.mark.asyncio
    async def test_set_limits_validates_input(self):
        """set_limits raises ValueError on invalid limits."""
        from src.greeks.limits_store import LimitsStore

        store = LimitsStore()
        invalid_limits = GreeksLimitSet(
            dollar_delta=ThresholdLevels(
                warn=Decimal("200"),  # Invalid: warn > crit
                crit=Decimal("100"),
                hard=Decimal("300"),
            ),
            gamma_dollar=ThresholdLevels(
                warn=Decimal("100"),
                crit=Decimal("150"),
                hard=Decimal("200"),
            ),
            vega_per_1pct=ThresholdLevels(
                warn=Decimal("100"),
                crit=Decimal("150"),
                hard=Decimal("200"),
            ),
            theta_per_day=ThresholdLevels(
                warn=Decimal("100"),
                crit=Decimal("150"),
                hard=Decimal("200"),
            ),
        )

        with pytest.raises(ValueError) as exc_info:
            await store.set_limits(
                account_id="acc_001",
                limits=invalid_limits,
                updated_by="user_123",
            )

        assert "dollar_delta" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_limits_returns_response_with_timestamp(self):
        """set_limits returns response with updated_at timestamp."""
        from src.greeks.limits_store import LimitsStore

        store = LimitsStore()
        before = datetime.now(timezone.utc)

        result = await store.set_limits(
            account_id="acc_001",
            limits=_make_limit_set(),
            updated_by="user_123",
        )

        after = datetime.now(timezone.utc)
        assert before <= result.updated_at <= after

    @pytest.mark.asyncio
    async def test_strategy_level_limits_returns_501(self):
        """Strategy-level limits return 501 Not Implemented."""
        from src.greeks.limits_store import LimitsStore, NotImplementedError

        store = LimitsStore()

        with pytest.raises(NotImplementedError):
            await store.set_limits(
                account_id="acc_001",
                limits=_make_limit_set(),
                updated_by="user_123",
                strategy_id="strat_001",
            )
