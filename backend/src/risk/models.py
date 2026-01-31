from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.greeks.v2_models import GreeksCheckResult
    from src.strategies.signals import Signal


@dataclass
class RiskResult:
    """Result of risk evaluation for a signal."""

    approved: bool
    signal: "Signal"
    rejection_reason: str | None = None
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
    greeks_check_result: "GreeksCheckResult | None" = None


@dataclass
class RiskConfig:
    """Configuration for risk management."""

    account_id: str

    # Position limits
    max_position_value: Decimal = Decimal("10000")
    max_position_pct: Decimal = Decimal("5")
    max_quantity_per_order: int = 500

    # Portfolio limits
    max_positions: int = 20
    max_exposure_pct: Decimal = Decimal("80")

    # Loss limits
    daily_loss_limit: Decimal = Decimal("1000")
    max_drawdown_pct: Decimal = Decimal("10")

    # Symbol restrictions
    blocked_symbols: list[str] = field(default_factory=list)
    allowed_symbols: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "RiskConfig":
        """Load configuration from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        risk_data = data.get("risk", {})

        return cls(
            account_id=risk_data["account_id"],
            max_position_value=Decimal(str(risk_data.get("max_position_value", 10000))),
            max_position_pct=Decimal(str(risk_data.get("max_position_pct", 5))),
            max_quantity_per_order=risk_data.get("max_quantity_per_order", 500),
            max_positions=risk_data.get("max_positions", 20),
            max_exposure_pct=Decimal(str(risk_data.get("max_exposure_pct", 80))),
            daily_loss_limit=Decimal(str(risk_data.get("daily_loss_limit", 1000))),
            max_drawdown_pct=Decimal(str(risk_data.get("max_drawdown_pct", 10))),
            blocked_symbols=risk_data.get("blocked_symbols", []),
            allowed_symbols=risk_data.get("allowed_symbols", []),
        )
