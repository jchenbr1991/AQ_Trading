# backend/src/strategies/signals.py
import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class Signal:
    """
    A trading signal emitted by a strategy.

    Signals express intent (buy/sell), not orders. Risk Manager
    validates and Order Manager executes.

    Attributes:
        strategy_id: Strategy identifier that generated this signal.
        symbol: Ticker symbol for the asset.
        action: Signal action - "buy" or "sell".
        quantity: Number of shares/units.
        order_type: Order type - "market" or "limit".
        limit_price: Limit price for limit orders.
        reason: Human-readable explanation for the signal.
        timestamp: Signal generation timestamp.
        factor_scores: Factor values at signal generation time for attribution.
            Example: {"momentum_factor": Decimal("0.035"), "composite": Decimal("0.028")}
    """

    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    factor_scores: dict[str, Decimal] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize Signal to JSON string."""
        return json.dumps(
            {
                "strategy_id": self.strategy_id,
                "symbol": self.symbol,
                "action": self.action,
                "quantity": self.quantity,
                "order_type": self.order_type,
                "limit_price": str(self.limit_price) if self.limit_price else None,
                "reason": self.reason,
                "timestamp": self.timestamp.isoformat(),
                "factor_scores": {k: str(v) for k, v in self.factor_scores.items()},
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "Signal":
        """Deserialize Signal from JSON string."""
        d = json.loads(data)
        # Parse factor_scores, defaulting to empty dict for backward compatibility
        factor_scores_raw = d.get("factor_scores", {})
        factor_scores = {k: Decimal(v) for k, v in factor_scores_raw.items()}
        return cls(
            strategy_id=d["strategy_id"],
            symbol=d["symbol"],
            action=d["action"],
            quantity=d["quantity"],
            order_type=d.get("order_type", "market"),
            limit_price=Decimal(d["limit_price"]) if d.get("limit_price") else None,
            reason=d.get("reason", ""),
            timestamp=datetime.fromisoformat(d["timestamp"])
            if d.get("timestamp")
            else datetime.utcnow(),
            factor_scores=factor_scores,
        )


@dataclass
class OrderFill:
    """
    Represents a fill (execution) of an order.

    CRITICAL: fill_id is the broker's unique trade/execution ID.
    Used for idempotency to prevent processing the same fill twice.
    """

    fill_id: str  # Broker's unique trade ID - CRITICAL for idempotency
    order_id: str  # Broker's order ID
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    timestamp: datetime

    def to_json(self) -> str:
        """Serialize OrderFill to JSON string."""
        return json.dumps(
            {
                "fill_id": self.fill_id,
                "order_id": self.order_id,
                "symbol": self.symbol,
                "side": self.side,
                "quantity": self.quantity,
                "price": str(self.price),
                "timestamp": self.timestamp.isoformat(),
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "OrderFill":
        """Deserialize OrderFill from JSON string."""
        d = json.loads(data)
        return cls(
            fill_id=d["fill_id"],
            order_id=d["order_id"],
            symbol=d["symbol"],
            side=d["side"],
            quantity=d["quantity"],
            price=Decimal(d["price"]),
            timestamp=datetime.fromisoformat(d["timestamp"]),
        )
