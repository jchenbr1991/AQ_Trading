import tempfile
from decimal import Decimal

import pytest
from src.risk.models import RiskConfig, RiskResult
from src.strategies.signals import Signal


class TestRiskConfig:
    def test_default_values(self):
        """RiskConfig has sensible defaults."""
        config = RiskConfig(account_id="ACC001")

        assert config.account_id == "ACC001"
        assert config.max_position_value == Decimal("10000")
        assert config.max_position_pct == Decimal("5")
        assert config.max_quantity_per_order == 500
        assert config.max_positions == 20
        assert config.max_exposure_pct == Decimal("80")
        assert config.daily_loss_limit == Decimal("1000")
        assert config.max_drawdown_pct == Decimal("10")
        assert config.blocked_symbols == []
        assert config.allowed_symbols == []

    def test_from_yaml(self):
        """Load config from YAML file."""
        yaml_content = """
risk:
  account_id: "TEST001"
  max_position_value: 5000
  max_position_pct: 3
  max_quantity_per_order: 100
  max_positions: 10
  max_exposure_pct: 50
  daily_loss_limit: 500
  max_drawdown_pct: 5
  blocked_symbols:
    - BANNED
  allowed_symbols: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = RiskConfig.from_yaml(f.name)

        assert config.account_id == "TEST001"
        assert config.max_position_value == Decimal("5000")
        assert config.max_position_pct == Decimal("3")
        assert config.max_quantity_per_order == 100
        assert config.max_positions == 10
        assert config.blocked_symbols == ["BANNED"]

    def test_from_yaml_missing_file(self):
        """Raise error for missing YAML file."""
        with pytest.raises(FileNotFoundError):
            RiskConfig.from_yaml("/nonexistent/path.yaml")


class TestRiskResult:
    def test_approved_result(self):
        """Create approved RiskResult."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = RiskResult(
            approved=True, signal=signal, checks_passed=["position_limits", "portfolio_limits"]
        )

        assert result.approved is True
        assert result.rejection_reason is None
        assert len(result.checks_passed) == 2
        assert len(result.checks_failed) == 0

    def test_rejected_result(self):
        """Create rejected RiskResult."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = RiskResult(
            approved=False,
            signal=signal,
            rejection_reason="position_limits",
            checks_passed=["symbol_allowed"],
            checks_failed=["position_limits"],
        )

        assert result.approved is False
        assert result.rejection_reason == "position_limits"
        assert "symbol_allowed" in result.checks_passed
        assert "position_limits" in result.checks_failed
