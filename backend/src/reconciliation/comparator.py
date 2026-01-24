"""Comparison logic for reconciliation."""

from datetime import datetime
from decimal import Decimal

from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import Position
from src.reconciliation.models import (
    DEFAULT_SEVERITY_MAP,
    Discrepancy,
    DiscrepancyType,
    ReconciliationConfig,
)


class Comparator:
    """Compares local state with broker state and identifies discrepancies."""

    def __init__(self, config: ReconciliationConfig):
        self._config = config

    def compare_positions(
        self,
        local: list[Position],
        broker: list[BrokerPosition],
    ) -> list[Discrepancy]:
        """Compare local positions against broker positions."""
        discrepancies: list[Discrepancy] = []
        now = datetime.utcnow()

        # Index by symbol for O(1) lookup
        local_by_symbol = {p.symbol: p for p in local}
        broker_by_symbol = {p.symbol: p for p in broker}

        all_symbols = set(local_by_symbol) | set(broker_by_symbol)

        for symbol in all_symbols:
            local_pos = local_by_symbol.get(symbol)
            broker_pos = broker_by_symbol.get(symbol)

            if local_pos is None:
                # MISSING_LOCAL: broker has position we don't
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.MISSING_LOCAL,
                        severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_LOCAL],
                        symbol=symbol,
                        local_value=None,
                        broker_value=broker_pos.quantity,
                        timestamp=now,
                        account_id=self._config.account_id,
                    )
                )
            elif broker_pos is None:
                # MISSING_BROKER: we have position broker doesn't
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.MISSING_BROKER,
                        severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_BROKER],
                        symbol=symbol,
                        local_value=local_pos.quantity,
                        broker_value=None,
                        timestamp=now,
                        account_id=self._config.account_id,
                    )
                )
            elif local_pos.quantity != broker_pos.quantity:
                # QUANTITY_MISMATCH
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.QUANTITY_MISMATCH,
                        severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.QUANTITY_MISMATCH],
                        symbol=symbol,
                        local_value=local_pos.quantity,
                        broker_value=broker_pos.quantity,
                        timestamp=now,
                        account_id=self._config.account_id,
                    )
                )
            elif local_pos.avg_cost != broker_pos.avg_cost:
                # COST_MISMATCH (informational)
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.COST_MISMATCH,
                        severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.COST_MISMATCH],
                        symbol=symbol,
                        local_value=local_pos.avg_cost,
                        broker_value=broker_pos.avg_cost,
                        timestamp=now,
                        account_id=self._config.account_id,
                    )
                )

        return discrepancies

    def compare_account(
        self,
        local_cash: Decimal,
        local_equity: Decimal,
        broker: BrokerAccount,
    ) -> list[Discrepancy]:
        """Compare local account values against broker account."""
        discrepancies: list[Discrepancy] = []
        now = datetime.utcnow()

        # Check cash with absolute tolerance
        cash_diff = abs(local_cash - broker.cash)
        if cash_diff > self._config.cash_tolerance:
            discrepancies.append(
                Discrepancy(
                    type=DiscrepancyType.CASH_MISMATCH,
                    severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.CASH_MISMATCH],
                    symbol=None,
                    local_value=local_cash,
                    broker_value=broker.cash,
                    timestamp=now,
                    account_id=self._config.account_id,
                )
            )

        # Check equity with percentage tolerance
        if local_equity != Decimal("0"):
            equity_diff_pct = abs(local_equity - broker.total_equity) / local_equity * 100
            if equity_diff_pct > self._config.equity_tolerance_pct:
                discrepancies.append(
                    Discrepancy(
                        type=DiscrepancyType.EQUITY_MISMATCH,
                        severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.EQUITY_MISMATCH],
                        symbol=None,
                        local_value=local_equity,
                        broker_value=broker.total_equity,
                        timestamp=now,
                        account_id=self._config.account_id,
                    )
                )

        return discrepancies
