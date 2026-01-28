"""End-to-end integration tests for Greeks monitoring system."""

from decimal import Decimal

from src.greeks.aggregator import GreeksAggregator
from src.greeks.alerts import AlertEngine
from src.greeks.calculator import (
    GreeksCalculator,
    ModelGreeksProvider,
    PositionInfo,
)
from src.greeks.models import (
    GreeksDataSource,
    GreeksLimitsConfig,
    GreeksThresholdConfig,
    RiskMetric,
)


class TestGreeksE2E:
    """End-to-end tests for Greeks system."""

    def test_full_calculation_pipeline(self):
        """Test complete pipeline: positions -> calculation -> aggregation -> alerts."""
        # 1. Setup positions
        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240621C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-06-21",
            ),
            PositionInfo(
                position_id=2,
                symbol="AAPL240621P00140000",
                underlying_symbol="AAPL",
                quantity=-5,
                multiplier=100,
                option_type="put",
                strike=Decimal("140.00"),
                expiry="2024-06-21",
            ),
        ]

        # 2. Calculate Greeks using model
        model_provider = ModelGreeksProvider(default_iv=Decimal("0.25"))
        model_provider.set_underlying_prices({"AAPL": Decimal("150.00")})
        calculator = GreeksCalculator(primary_provider=model_provider)

        position_greeks = calculator.calculate(positions)

        assert len(position_greeks) == 2
        assert all(pg.valid for pg in position_greeks)

        # 3. Aggregate
        aggregator = GreeksAggregator()
        account_greeks = aggregator.aggregate(position_greeks, "ACCOUNT", "acc123")

        assert account_greeks.valid_legs_count == 2
        assert account_greeks.total_legs_count == 2
        # Long call + short put = net long delta
        assert account_greeks.dollar_delta != 0

        # 4. Check alerts
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc123",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("1000"),  # Low limit to trigger alert
                ),
            },
        )

        engine = AlertEngine()
        alerts = engine.check_alerts(account_greeks, config)

        # Should have delta alert due to low limit
        assert len(alerts) > 0

    def test_model_fallback_works(self):
        """Test that model fallback works when Futu unavailable."""
        positions = [
            PositionInfo(
                position_id=1,
                symbol="TSLA240621C00200000",
                underlying_symbol="TSLA",
                quantity=5,
                multiplier=100,
                option_type="call",
                strike=Decimal("200.00"),
                expiry="2024-06-21",
            ),
        ]

        # Empty Futu provider (simulates unavailable)
        class EmptyFutu:
            @property
            def source(self):
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions):
                return {}

        # Model fallback
        model = ModelGreeksProvider()
        model.set_underlying_prices({"TSLA": Decimal("200.00")})

        calculator = GreeksCalculator(
            primary_provider=EmptyFutu(),
            fallback_provider=model,
        )

        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].valid is True
        assert results[0].source == GreeksDataSource.MODEL
