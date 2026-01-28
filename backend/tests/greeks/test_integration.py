"""Integration tests for Greeks monitoring pipeline.

Tests cover end-to-end scenarios:
- Task 28: Full pipeline integration (Calculate -> Aggregate -> Alert)
- Task 29: Alert lifecycle (escalation, hysteresis recovery, deduplication)
- Task 30: ROC detection end-to-end
- Multi-strategy scenarios
- Edge cases and error handling
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from src.greeks.aggregator import (
    GAMMA_HIGH_RISK_THRESHOLD,
    VEGA_HIGH_RISK_THRESHOLD,
    GreeksAggregator,
)
from src.greeks.alerts import AlertEngine
from src.greeks.calculator import (
    PositionInfo,
    RawGreeks,
    convert_to_dollar_greeks,
)
from src.greeks.models import (
    AggregatedGreeks,
    GreeksDataSource,
    GreeksLevel,
    GreeksLimitsConfig,
    GreeksThresholdConfig,
    PositionGreeks,
    RiskMetric,
)


def _make_position_info(
    position_id: int,
    symbol: str = "AAPL240119C00150000",
    underlying_symbol: str = "AAPL",
    quantity: int = 10,
    multiplier: int = 100,
    option_type: str = "call",
    strike: Decimal = Decimal("150.00"),
    expiry: str = "2024-01-19",
) -> PositionInfo:
    """Factory function to create PositionInfo for testing."""
    return PositionInfo(
        position_id=position_id,
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        quantity=quantity,
        multiplier=multiplier,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
    )


def _make_raw_greeks(
    delta: Decimal = Decimal("0.5"),
    gamma: Decimal = Decimal("0.05"),
    vega: Decimal = Decimal("0.15"),
    theta: Decimal = Decimal("-0.05"),
    implied_vol: Decimal = Decimal("0.25"),
    underlying_price: Decimal = Decimal("150.00"),
) -> RawGreeks:
    """Factory function to create RawGreeks for testing."""
    return RawGreeks(
        delta=delta,
        gamma=gamma,
        vega=vega,
        theta=theta,
        implied_vol=implied_vol,
        underlying_price=underlying_price,
    )


def _make_position_greeks(
    position_id: int,
    symbol: str = "AAPL240119C00150000",
    underlying_symbol: str = "AAPL",
    quantity: int = 10,
    multiplier: int = 100,
    underlying_price: Decimal = Decimal("150.00"),
    option_type: str = "call",
    strike: Decimal = Decimal("150.00"),
    expiry: str = "2024-01-19",
    dollar_delta: Decimal = Decimal("5000.00"),
    gamma_dollar: Decimal = Decimal("100.00"),
    gamma_pnl_1pct: Decimal = Decimal("0.50"),
    vega_per_1pct: Decimal = Decimal("200.00"),
    theta_per_day: Decimal = Decimal("-50.00"),
    valid: bool = True,
    quality_warnings: list[str] | None = None,
    as_of_ts: datetime | None = None,
    strategy_id: str | None = None,
) -> PositionGreeks:
    """Factory function to create PositionGreeks for testing."""
    return PositionGreeks(
        position_id=position_id,
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        quantity=quantity,
        multiplier=multiplier,
        underlying_price=underlying_price,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        source=GreeksDataSource.FUTU,
        model=None,
        valid=valid,
        quality_warnings=quality_warnings or [],
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
        strategy_id=strategy_id,
    )


def _make_aggregated_greeks(
    scope: str = "ACCOUNT",
    scope_id: str = "acc_001",
    dollar_delta: Decimal = Decimal("0"),
    gamma_dollar: Decimal = Decimal("0"),
    vega_per_1pct: Decimal = Decimal("0"),
    theta_per_day: Decimal = Decimal("0"),
    as_of_ts: datetime | None = None,
    valid_legs_count: int = 0,
    total_legs_count: int = 0,
    valid_notional: Decimal = Decimal("0"),
    total_notional: Decimal = Decimal("0"),
    has_positions: bool = True,
) -> AggregatedGreeks:
    """Factory function to create AggregatedGreeks for testing."""
    return AggregatedGreeks(
        scope=scope,
        scope_id=scope_id,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
        valid_legs_count=valid_legs_count,
        total_legs_count=total_legs_count,
        valid_notional=valid_notional,
        total_notional=total_notional,
        has_positions=has_positions,
    )


class TestFullPipelineIntegration:
    """End-to-end tests for the full Greeks monitoring pipeline.

    Task 28: Full Pipeline Integration Test
    """

    def test_full_pipeline_calculate_aggregate_alert(self):
        """Test: Calculate -> Aggregate -> Check Alerts flow.

        1. Create mock positions with known Greeks
        2. Calculate dollar Greeks
        3. Aggregate to account level
        4. Check for threshold alerts
        5. Verify alerts are generated correctly
        """
        # Step 1: Create position info and raw Greeks
        position = _make_position_info(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
        )

        raw = _make_raw_greeks(
            delta=Decimal("0.6"),  # Per-share delta
            gamma=Decimal("0.04"),
            vega=Decimal("0.20"),
            theta=Decimal("-0.06"),
            underlying_price=Decimal("150.00"),
        )

        # Step 2: Calculate dollar Greeks
        position_greeks = convert_to_dollar_greeks(
            position=position,
            raw=raw,
            source=GreeksDataSource.FUTU,
        )

        # Verify dollar Greeks calculation
        # dollar_delta = 0.6 * 10 * 100 * 150 = 90000
        expected_dollar_delta = Decimal("0.6") * 10 * 100 * Decimal("150")
        assert position_greeks.dollar_delta == expected_dollar_delta
        assert position_greeks.valid is True

        # Step 3: Aggregate to account level
        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(
            positions=[position_greeks],
            scope="ACCOUNT",
            scope_id="acc_001",
        )

        assert aggregated.dollar_delta == expected_dollar_delta
        assert aggregated.valid_legs_count == 1
        assert aggregated.total_legs_count == 1

        # Step 4: Check for threshold alerts
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),  # warn at 40000, crit at 50000
                ),
            },
        )

        alerts = engine.check_alerts(aggregated, config)

        # Step 5: Verify alerts
        # 90000 > 60000 (hard = 50000 * 1.2), so should be HARD level
        assert len(alerts) == 1
        assert alerts[0].alert_type == "THRESHOLD"
        assert alerts[0].metric == RiskMetric.DELTA
        assert alerts[0].level == GreeksLevel.HARD
        assert alerts[0].current_value == expected_dollar_delta

    def test_pipeline_with_mixed_validity(self):
        """Test pipeline handles mix of valid and invalid positions."""
        # Create positions with mixed validity
        positions = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("30000"),
                gamma_dollar=Decimal("500"),
                vega_per_1pct=Decimal("1000"),
                theta_per_day=Decimal("-200"),
                valid=True,
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("20000"),  # Should not be counted
                valid=False,
                quality_warnings=["No Greeks data available"],
            ),
            _make_position_greeks(
                position_id=3,
                dollar_delta=Decimal("15000"),
                gamma_dollar=Decimal("300"),
                vega_per_1pct=Decimal("500"),
                theta_per_day=Decimal("-100"),
                valid=True,
            ),
        ]

        # Aggregate
        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(
            positions=positions,
            scope="ACCOUNT",
            scope_id="acc_001",
        )

        # Only valid positions should be aggregated
        assert aggregated.dollar_delta == Decimal("45000")  # 30000 + 15000
        assert aggregated.gamma_dollar == Decimal("800")  # 500 + 300
        assert aggregated.vega_per_1pct == Decimal("1500")  # 1000 + 500
        assert aggregated.theta_per_day == Decimal("-300")  # -200 + -100
        assert aggregated.valid_legs_count == 2
        assert aggregated.total_legs_count == 3
        assert 2 in aggregated.missing_positions

        # Check alerts
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),  # warn at 40000
                ),
            },
        )

        alerts = engine.check_alerts(aggregated, config)

        # 45000 > 40000 (warn threshold)
        assert len(alerts) == 1
        assert alerts[0].level == GreeksLevel.WARN

    def test_pipeline_coverage_alert(self):
        """Test coverage alert when too many positions are invalid.

        Note: Coverage is tracked via aggregated.coverage_pct and
        is_coverage_sufficient. The AlertEngine does not directly
        generate coverage alerts in V1, but the aggregated object
        provides coverage metrics for external systems to act on.
        """
        # Create positions where coverage is < 95%
        positions = [
            _make_position_greeks(
                position_id=1,
                quantity=10,
                underlying_price=Decimal("100"),  # notional = 100000
                valid=True,
            ),
            _make_position_greeks(
                position_id=2,
                quantity=10,
                underlying_price=Decimal("100"),  # notional = 100000
                valid=False,
            ),
            _make_position_greeks(
                position_id=3,
                quantity=10,
                underlying_price=Decimal("100"),  # notional = 100000
                valid=False,
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(
            positions=positions,
            scope="ACCOUNT",
            scope_id="acc_001",
        )

        # Coverage = 100000 / 300000 = 33.3%
        assert aggregated.valid_notional == Decimal("100000")
        assert aggregated.total_notional == Decimal("300000")
        assert aggregated.coverage_pct < Decimal("95.0")
        assert aggregated.is_coverage_sufficient is False


class TestAlertLifecycleIntegration:
    """Tests for the complete alert lifecycle.

    Task 29: Alert Lifecycle Test
    """

    def test_alert_escalation_warn_to_crit_to_hard(self):
        """Test alert level escalates as values increase.

        1. Start below warn threshold -> NORMAL
        2. Cross warn threshold -> WARN alert
        3. Cross crit threshold -> CRIT alert
        4. Cross hard threshold -> HARD alert
        """
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    # warn = 40000, crit = 50000, hard = 60000
                ),
            },
        )

        # 1. Start below warn threshold -> NORMAL (no alert)
        aggregated_normal = _make_aggregated_greeks(
            dollar_delta=Decimal("30000"),
        )
        alerts = engine.check_alerts(aggregated_normal, config)
        assert len(alerts) == 0
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state is not None
        assert state.current_level == GreeksLevel.NORMAL

        # 2. Cross warn threshold -> WARN alert
        aggregated_warn = _make_aggregated_greeks(
            dollar_delta=Decimal("45000"),
        )
        alerts = engine.check_alerts(aggregated_warn, config)
        assert len(alerts) == 1
        assert alerts[0].level == GreeksLevel.WARN
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state.current_level == GreeksLevel.WARN

        # 3. Cross crit threshold -> CRIT alert
        aggregated_crit = _make_aggregated_greeks(
            dollar_delta=Decimal("55000"),
        )
        alerts = engine.check_alerts(aggregated_crit, config)
        assert len(alerts) == 1
        assert alerts[0].level == GreeksLevel.CRIT
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state.current_level == GreeksLevel.CRIT

        # 4. Cross hard threshold -> HARD alert
        aggregated_hard = _make_aggregated_greeks(
            dollar_delta=Decimal("65000"),
        )
        alerts = engine.check_alerts(aggregated_hard, config)
        assert len(alerts) == 1
        assert alerts[0].level == GreeksLevel.HARD
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state.current_level == GreeksLevel.HARD

    def test_alert_recovery_with_hysteresis(self):
        """Test alert clears only when below recovery threshold.

        1. Trigger WARN alert at 80% (40000)
        2. Drop to 78% (39000) -> still WARN (above 75% recovery = 37500)
        3. Drop to 74% (37000) -> clears to NORMAL
        """
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    warn_pct=Decimal("0.80"),  # warn at 40000
                    warn_recover_pct=Decimal("0.75"),  # recover at 37500
                ),
            },
        )

        # 1. Trigger WARN alert at 80%
        aggregated_warn = _make_aggregated_greeks(
            dollar_delta=Decimal("42000"),  # Above warn (40000)
        )
        alerts = engine.check_alerts(aggregated_warn, config)
        assert len(alerts) == 1
        assert alerts[0].level == GreeksLevel.WARN

        # 2. Drop to 78% (39000) -> still WARN (above 75% recovery = 37500)
        aggregated_still_warn = _make_aggregated_greeks(
            dollar_delta=Decimal("39000"),  # Below warn but above recover
        )
        alerts = engine.check_alerts(aggregated_still_warn, config)
        # No new alert generated (same level, dedupe applies)
        # But state should still be WARN due to hysteresis
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state.current_level == GreeksLevel.WARN

        # 3. Drop to 74% (37000) -> clears to NORMAL
        aggregated_normal = _make_aggregated_greeks(
            dollar_delta=Decimal("37000"),  # Below recover (37500)
        )
        alerts = engine.check_alerts(aggregated_normal, config)
        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state.current_level == GreeksLevel.NORMAL

    def test_alert_deduplication(self):
        """Test duplicate alerts are suppressed within window."""
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
            dedupe_window_seconds_by_level={
                GreeksLevel.WARN: 900,  # 15 minutes
                GreeksLevel.CRIT: 300,
                GreeksLevel.HARD: 60,
            },
        )

        # First check - generates alert
        aggregated = _make_aggregated_greeks(
            dollar_delta=Decimal("45000"),
        )
        alerts_first = engine.check_alerts(aggregated, config)
        assert len(alerts_first) == 1
        assert alerts_first[0].level == GreeksLevel.WARN

        # Second check immediately after - deduplicated (no alert)
        alerts_second = engine.check_alerts(aggregated, config)
        assert len(alerts_second) == 0

        # Third check - still deduplicated
        aggregated_similar = _make_aggregated_greeks(
            dollar_delta=Decimal("46000"),  # Slightly different value, same level
        )
        alerts_third = engine.check_alerts(aggregated_similar, config)
        assert len(alerts_third) == 0

    def test_alert_deduplication_allows_escalation(self):
        """Test that deduplication does not block escalation alerts."""
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
            dedupe_window_seconds_by_level={
                GreeksLevel.WARN: 900,
                GreeksLevel.CRIT: 300,
                GreeksLevel.HARD: 60,
            },
        )

        # First check - WARN alert
        aggregated_warn = _make_aggregated_greeks(
            dollar_delta=Decimal("45000"),
        )
        alerts_warn = engine.check_alerts(aggregated_warn, config)
        assert len(alerts_warn) == 1
        assert alerts_warn[0].level == GreeksLevel.WARN

        # Immediately escalate to CRIT - should generate new alert
        aggregated_crit = _make_aggregated_greeks(
            dollar_delta=Decimal("55000"),
        )
        alerts_crit = engine.check_alerts(aggregated_crit, config)
        assert len(alerts_crit) == 1
        assert alerts_crit[0].level == GreeksLevel.CRIT


class TestROCDetectionIntegration:
    """Tests for Rate-of-Change detection end-to-end.

    Task 30: ROC Detection E2E Test
    """

    def test_roc_alert_on_rapid_delta_change(self):
        """Test ROC alert triggers on rapid delta change.

        1. Create initial state with delta = 30000
        2. Simulate jump to delta = 45000 (50% of limit)
        3. Verify ROC alert generated
        """
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    rate_change_pct=Decimal("0.20"),  # 20% = 10000
                    rate_change_abs=Decimal("5000"),
                ),
            },
        )

        # Previous Greeks snapshot
        prev_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("30000"),
        )

        # Current Greeks with rapid change
        current_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("45000"),  # Change of 15000
        )

        alerts = engine.check_alerts(current_greeks, config, prev_greeks=prev_greeks)

        # Should have ROC alert (change of 15000 > rate_change_abs 5000)
        roc_alerts = [a for a in alerts if a.alert_type == "ROC"]
        assert len(roc_alerts) == 1
        assert roc_alerts[0].metric == RiskMetric.DELTA
        assert roc_alerts[0].prev_value == Decimal("30000")
        assert roc_alerts[0].current_value == Decimal("45000")

    def test_roc_uses_prev_greeks_from_snapshot(self):
        """Test ROC detection uses prev_greeks parameter.

        Critical: ROC must use persisted snapshot, not memory state.
        """
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    rate_change_abs=Decimal("5000"),
                ),
            },
        )

        # First, establish state with initial value
        initial_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("30000"),
        )
        engine.check_alerts(initial_greeks, config)

        # Now check with a new value but passing explicit prev_greeks
        # This simulates using persisted snapshot data
        snapshot_prev = _make_aggregated_greeks(
            dollar_delta=Decimal("25000"),  # Different from what engine saw
        )

        current_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("35000"),  # Change of 10000 from snapshot
        )

        alerts = engine.check_alerts(current_greeks, config, prev_greeks=snapshot_prev)

        # ROC should use snapshot value (25000), not engine state (30000)
        roc_alerts = [a for a in alerts if a.alert_type == "ROC"]
        assert len(roc_alerts) == 1
        assert roc_alerts[0].prev_value == Decimal("25000")  # From snapshot
        assert roc_alerts[0].current_value == Decimal("35000")

    def test_no_roc_alert_for_gradual_change(self):
        """Test no ROC alert for slow gradual changes."""
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    rate_change_pct=Decimal("0.20"),  # 20% = 10000
                    rate_change_abs=Decimal("5000"),
                ),
            },
        )

        # Previous snapshot
        prev_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("30000"),
        )

        # Current with small change
        current_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("33000"),  # Change of 3000, below 5000 threshold
        )

        alerts = engine.check_alerts(current_greeks, config, prev_greeks=prev_greeks)

        # No ROC alert should be generated
        roc_alerts = [a for a in alerts if a.alert_type == "ROC"]
        assert len(roc_alerts) == 0

    def test_roc_alert_on_rapid_decrease(self):
        """Test ROC alert triggers on rapid decrease."""
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    rate_change_abs=Decimal("5000"),
                ),
            },
        )

        prev_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("40000"),
        )

        current_greeks = _make_aggregated_greeks(
            dollar_delta=Decimal("25000"),  # Decrease of 15000
        )

        alerts = engine.check_alerts(current_greeks, config, prev_greeks=prev_greeks)

        # Should have ROC alert (change of -15000 has abs > 5000)
        roc_alerts = [a for a in alerts if a.alert_type == "ROC"]
        assert len(roc_alerts) == 1


class TestMultiStrategyIntegration:
    """Tests for multi-strategy scenarios."""

    def test_strategy_isolation(self):
        """Test alerts are per-strategy, not account-wide."""
        engine = AlertEngine()

        # Strategy-level config for strategy_a
        config_a = GreeksLimitsConfig(
            scope="STRATEGY",
            scope_id="strategy_a",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("20000"),  # warn at 16000
                ),
            },
        )

        # Strategy-level config for strategy_b
        config_b = GreeksLimitsConfig(
            scope="STRATEGY",
            scope_id="strategy_b",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("30000"),  # warn at 24000
                ),
            },
        )

        # Strategy A: above its warn threshold
        aggregated_a = _make_aggregated_greeks(
            scope="STRATEGY",
            scope_id="strategy_a",
            dollar_delta=Decimal("18000"),  # Above 16000 warn
        )

        # Strategy B: below its warn threshold
        aggregated_b = _make_aggregated_greeks(
            scope="STRATEGY",
            scope_id="strategy_b",
            dollar_delta=Decimal("20000"),  # Below 24000 warn
        )

        alerts_a = engine.check_alerts(aggregated_a, config_a)
        alerts_b = engine.check_alerts(aggregated_b, config_b)

        # Strategy A should have alert
        assert len(alerts_a) == 1
        assert alerts_a[0].scope == "STRATEGY"
        assert alerts_a[0].scope_id == "strategy_a"
        assert alerts_a[0].level == GreeksLevel.WARN

        # Strategy B should NOT have alert
        assert len(alerts_b) == 0

        # States should be independent
        state_a = engine.get_state("STRATEGY", "strategy_a", RiskMetric.DELTA)
        state_b = engine.get_state("STRATEGY", "strategy_b", RiskMetric.DELTA)
        assert state_a.current_level == GreeksLevel.WARN
        assert state_b.current_level == GreeksLevel.NORMAL

    def test_account_aggregates_all_strategies(self):
        """Test account total includes all strategies."""
        aggregator = GreeksAggregator()

        positions = [
            # Strategy A positions
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("10000"),
                gamma_dollar=Decimal("200"),
                vega_per_1pct=Decimal("500"),
                theta_per_day=Decimal("-100"),
                strategy_id="strategy_a",
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("5000"),
                gamma_dollar=Decimal("150"),
                vega_per_1pct=Decimal("300"),
                theta_per_day=Decimal("-75"),
                strategy_id="strategy_a",
            ),
            # Strategy B positions
            _make_position_greeks(
                position_id=3,
                dollar_delta=Decimal("-3000"),
                gamma_dollar=Decimal("100"),
                vega_per_1pct=Decimal("200"),
                theta_per_day=Decimal("-50"),
                strategy_id="strategy_b",
            ),
            # Unassigned position
            _make_position_greeks(
                position_id=4,
                dollar_delta=Decimal("2000"),
                gamma_dollar=Decimal("80"),
                vega_per_1pct=Decimal("100"),
                theta_per_day=Decimal("-25"),
                strategy_id=None,
            ),
        ]

        account_total, strategy_dict = aggregator.aggregate_by_strategy(positions, "acc_001")

        # Account total should include all positions
        assert account_total.dollar_delta == Decimal("14000")  # 10000+5000-3000+2000
        assert account_total.gamma_dollar == Decimal("530")  # 200+150+100+80
        assert account_total.valid_legs_count == 4

        # Strategy breakdown
        assert "strategy_a" in strategy_dict
        assert "strategy_b" in strategy_dict
        assert "_unassigned_" in strategy_dict

        assert strategy_dict["strategy_a"].dollar_delta == Decimal("15000")
        assert strategy_dict["strategy_a"].valid_legs_count == 2

        assert strategy_dict["strategy_b"].dollar_delta == Decimal("-3000")
        assert strategy_dict["strategy_b"].valid_legs_count == 1

        assert strategy_dict["_unassigned_"].dollar_delta == Decimal("2000")
        assert strategy_dict["_unassigned_"].valid_legs_count == 1


class TestEdgeCasesIntegration:
    """Tests for edge cases and error handling."""

    def test_empty_positions_no_crash(self):
        """Test monitoring handles empty position list."""
        aggregator = GreeksAggregator()
        engine = AlertEngine()

        # Empty aggregation
        aggregated = aggregator.aggregate([], scope="ACCOUNT", scope_id="acc_001")

        assert aggregated.has_positions is False
        assert aggregated.dollar_delta == Decimal("0")
        assert aggregated.coverage_pct == Decimal("100.0")

        # Alert engine should handle empty aggregation
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
        )

        alerts = engine.check_alerts(aggregated, config)
        assert len(alerts) == 0  # No alerts for empty portfolio

    def test_all_invalid_positions(self):
        """Test 100% invalid positions generates coverage alert."""
        positions = [
            _make_position_greeks(
                position_id=1,
                quantity=10,
                underlying_price=Decimal("100"),
                valid=False,
            ),
            _make_position_greeks(
                position_id=2,
                quantity=10,
                underlying_price=Decimal("100"),
                valid=False,
            ),
            _make_position_greeks(
                position_id=3,
                quantity=10,
                underlying_price=Decimal("100"),
                valid=False,
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # All positions invalid
        assert aggregated.valid_legs_count == 0
        assert aggregated.total_legs_count == 3
        assert aggregated.valid_notional == Decimal("0")
        assert aggregated.total_notional > Decimal("0")
        assert aggregated.coverage_pct == Decimal("0")
        assert aggregated.is_coverage_sufficient is False

        # All positions should be in missing list
        assert 1 in aggregated.missing_positions
        assert 2 in aggregated.missing_positions
        assert 3 in aggregated.missing_positions

    def test_high_risk_missing_legs_detection(self):
        """Test high gamma/vega missing positions are flagged."""
        positions = [
            # Valid position
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("10000"),
                gamma_dollar=Decimal("200"),
                vega_per_1pct=Decimal("500"),
                valid=True,
            ),
            # Invalid position with HIGH gamma (above threshold)
            _make_position_greeks(
                position_id=2,
                gamma_dollar=Decimal(str(GAMMA_HIGH_RISK_THRESHOLD + 500)),
                vega_per_1pct=Decimal("100"),
                valid=False,
            ),
            # Invalid position with HIGH vega (above threshold)
            _make_position_greeks(
                position_id=3,
                gamma_dollar=Decimal("100"),
                vega_per_1pct=Decimal(str(VEGA_HIGH_RISK_THRESHOLD + 500)),
                valid=False,
            ),
            # Invalid position with LOW gamma/vega (not high risk)
            _make_position_greeks(
                position_id=4,
                gamma_dollar=Decimal("50"),
                vega_per_1pct=Decimal("100"),
                valid=False,
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # Should flag high risk missing legs
        assert aggregated.has_high_risk_missing_legs is True
        assert 2 in aggregated.missing_positions
        assert 3 in aggregated.missing_positions
        assert 4 in aggregated.missing_positions

    def test_single_position_aggregation(self):
        """Test aggregation with single position works correctly."""
        position = _make_position_greeks(
            position_id=1,
            dollar_delta=Decimal("25000"),
            gamma_dollar=Decimal("500"),
            vega_per_1pct=Decimal("1000"),
            theta_per_day=Decimal("-200"),
        )

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate([position], scope="ACCOUNT", scope_id="acc_001")

        assert aggregated.dollar_delta == Decimal("25000")
        assert aggregated.gamma_dollar == Decimal("500")
        assert aggregated.valid_legs_count == 1
        assert aggregated.coverage_pct == Decimal("100.0")

    def test_mixed_positive_negative_greeks(self):
        """Test aggregation correctly handles mixed positive/negative Greeks."""
        positions = [
            # Long call (positive delta)
            _make_position_greeks(
                position_id=1,
                option_type="call",
                quantity=10,
                dollar_delta=Decimal("50000"),
                gamma_dollar=Decimal("1000"),
                vega_per_1pct=Decimal("2000"),
                theta_per_day=Decimal("-500"),
            ),
            # Short put (also positive delta)
            _make_position_greeks(
                position_id=2,
                option_type="put",
                quantity=-10,
                dollar_delta=Decimal("30000"),
                gamma_dollar=Decimal("-800"),  # Short gamma
                vega_per_1pct=Decimal("-1500"),  # Short vega
                theta_per_day=Decimal("400"),  # Positive theta (short option)
            ),
            # Long put (negative delta)
            _make_position_greeks(
                position_id=3,
                option_type="put",
                quantity=5,
                dollar_delta=Decimal("-20000"),
                gamma_dollar=Decimal("500"),
                vega_per_1pct=Decimal("800"),
                theta_per_day=Decimal("-200"),
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # Net delta: 50000 + 30000 - 20000 = 60000
        assert aggregated.dollar_delta == Decimal("60000")
        # Net gamma: 1000 - 800 + 500 = 700
        assert aggregated.gamma_dollar == Decimal("700")
        # Net vega: 2000 - 1500 + 800 = 1300
        assert aggregated.vega_per_1pct == Decimal("1300")
        # Net theta: -500 + 400 - 200 = -300
        assert aggregated.theta_per_day == Decimal("-300")

    def test_extreme_values_handling(self):
        """Test system handles extreme values without overflow."""
        positions = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("999999999.99"),
                gamma_dollar=Decimal("999999.99"),
                vega_per_1pct=Decimal("999999.99"),
                theta_per_day=Decimal("-999999.99"),
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("-999999999.99"),
                gamma_dollar=Decimal("999999.99"),
                vega_per_1pct=Decimal("999999.99"),
                theta_per_day=Decimal("-999999.99"),
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # Should handle without error
        assert aggregated.dollar_delta == Decimal("0")  # Cancels out
        assert aggregated.gamma_dollar == Decimal("1999999.98")  # Adds up

    def test_alert_engine_handles_multiple_metrics_simultaneously(self):
        """Test AlertEngine correctly processes multiple metrics at once."""
        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),  # warn at 40000
                ),
                RiskMetric.GAMMA: GreeksThresholdConfig(
                    metric=RiskMetric.GAMMA,
                    limit=Decimal("10000"),  # warn at 8000
                ),
                RiskMetric.VEGA: GreeksThresholdConfig(
                    metric=RiskMetric.VEGA,
                    limit=Decimal("20000"),  # warn at 16000
                ),
                RiskMetric.THETA: GreeksThresholdConfig(
                    metric=RiskMetric.THETA,
                    limit=Decimal("5000"),  # warn at 4000
                ),
            },
        )

        # All metrics above their warn thresholds
        aggregated = _make_aggregated_greeks(
            dollar_delta=Decimal("45000"),  # WARN
            gamma_dollar=Decimal("11000"),  # CRIT (above 10000)
            vega_per_1pct=Decimal("25000"),  # HARD (above 24000 = 20000 * 1.2)
            theta_per_day=Decimal("-4500"),  # WARN (abs value)
        )

        alerts = engine.check_alerts(aggregated, config)

        # Should have alerts for all 4 metrics
        assert len(alerts) == 4

        metrics_alerted = {a.metric for a in alerts}
        assert RiskMetric.DELTA in metrics_alerted
        assert RiskMetric.GAMMA in metrics_alerted
        assert RiskMetric.VEGA in metrics_alerted
        assert RiskMetric.THETA in metrics_alerted

        # Verify correct levels
        delta_alert = next(a for a in alerts if a.metric == RiskMetric.DELTA)
        gamma_alert = next(a for a in alerts if a.metric == RiskMetric.GAMMA)
        vega_alert = next(a for a in alerts if a.metric == RiskMetric.VEGA)
        theta_alert = next(a for a in alerts if a.metric == RiskMetric.THETA)

        assert delta_alert.level == GreeksLevel.WARN
        assert gamma_alert.level == GreeksLevel.CRIT
        assert vega_alert.level == GreeksLevel.HARD
        assert theta_alert.level == GreeksLevel.WARN

    def test_timestamp_propagation_through_pipeline(self):
        """Test that timestamps are correctly propagated through the pipeline."""
        now = datetime.now(timezone.utc)
        ts_old = now - timedelta(minutes=5)
        ts_new = now - timedelta(minutes=1)

        positions = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("10000"),
                as_of_ts=ts_old,
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("20000"),
                as_of_ts=ts_new,
            ),
        ]

        aggregator = GreeksAggregator()
        aggregated = aggregator.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # as_of_ts should be the minimum (most conservative)
        assert aggregated.as_of_ts == ts_old
        assert aggregated.as_of_ts_min == ts_old
        assert aggregated.as_of_ts_max == ts_new
