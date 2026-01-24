"""Tests for ReconciliationService."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import AssetType, Position
from src.reconciliation.models import DiscrepancyType, ReconciliationConfig
from src.reconciliation.service import ReconciliationService


@pytest.fixture
def mock_broker_query():
    broker = MagicMock()
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_account = AsyncMock(
        return_value=BrokerAccount(
            account_id="ACC001",
            cash=Decimal("100000.00"),
            buying_power=Decimal("200000.00"),
            total_equity=Decimal("100000.00"),
            margin_used=Decimal("0.00"),
        )
    )
    return broker


@pytest.fixture
def mock_position_provider():
    provider = MagicMock()
    provider.get_positions = AsyncMock(return_value=[])
    provider.get_cash = AsyncMock(return_value=Decimal("100000.00"))
    provider.get_equity = AsyncMock(return_value=Decimal("100000.00"))
    return provider


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def config():
    return ReconciliationConfig(account_id="ACC001")


@pytest.fixture
def service(mock_broker_query, mock_position_provider, mock_redis, config):
    return ReconciliationService(
        position_provider=mock_position_provider,
        broker_query=mock_broker_query,
        redis=mock_redis,
        config=config,
    )


class TestOnDemandReconcile:
    @pytest.mark.asyncio
    async def test_reconcile_clean_result(self, service):
        """On-demand reconcile returns clean result when matching."""
        result = await service.reconcile()
        assert result.is_clean is True
        assert result.discrepancies == []
        assert result.account_id == "ACC001"
        assert result.context == {"trigger": "on_demand"}

    @pytest.mark.asyncio
    async def test_reconcile_finds_discrepancies(
        self, service, mock_broker_query, mock_position_provider
    ):
        """On-demand reconcile detects discrepancies."""
        # Local has AAPL, broker doesn't
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        result = await service.reconcile()
        assert result.is_clean is False
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].type == DiscrepancyType.MISSING_BROKER

    @pytest.mark.asyncio
    async def test_reconcile_measures_duration(self, service):
        """Reconcile records duration_ms."""
        result = await service.reconcile()
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_reconcile_counts_positions(
        self, service, mock_broker_query, mock_position_provider
    ):
        """Reconcile counts positions checked."""
        broker_positions = [
            BrokerPosition("AAPL", 100, Decimal("150.00"), Decimal("15000.00"), AssetType.STOCK),
            BrokerPosition("GOOG", 50, Decimal("2800.00"), Decimal("140000.00"), AssetType.STOCK),
        ]
        mock_broker_query.get_positions.return_value = broker_positions
        mock_position_provider.get_positions.return_value = []

        result = await service.reconcile()
        assert result.positions_checked == 2


class TestRedisPublishing:
    @pytest.mark.asyncio
    async def test_publishes_result_to_redis(self, service, mock_redis):
        """Reconcile publishes result to reconciliation:result channel."""
        result = await service.reconcile()

        mock_redis.publish.assert_called()
        calls = mock_redis.publish.call_args_list
        result_calls = [c for c in calls if c[0][0] == "reconciliation:result"]
        assert len(result_calls) == 1

        payload = json.loads(result_calls[0][0][1])
        assert payload["account_id"] == "ACC001"
        assert payload["is_clean"] is True
        assert "run_id" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_publishes_discrepancies_to_redis(
        self, service, mock_broker_query, mock_position_provider, mock_redis
    ):
        """Each discrepancy is published separately."""
        # Create discrepancy scenario
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        await service.reconcile()

        calls = mock_redis.publish.call_args_list
        discrepancy_calls = [c for c in calls if c[0][0] == "reconciliation:discrepancy"]
        assert len(discrepancy_calls) == 1

        payload = json.loads(discrepancy_calls[0][0][1])
        assert payload["type"] == "missing_broker"
        assert payload["severity"] == "critical"
        assert payload["symbol"] == "AAPL"
        assert "run_id" in payload  # Correlates with result

    @pytest.mark.asyncio
    async def test_run_id_correlates_result_and_discrepancies(
        self, service, mock_broker_query, mock_position_provider, mock_redis
    ):
        """run_id matches between result and discrepancies."""
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        await service.reconcile()

        calls = mock_redis.publish.call_args_list
        result_payload = json.loads(
            [c for c in calls if c[0][0] == "reconciliation:result"][0][0][1]
        )
        discrepancy_payload = json.loads(
            [c for c in calls if c[0][0] == "reconciliation:discrepancy"][0][0][1]
        )

        assert result_payload["run_id"] == discrepancy_payload["run_id"]
