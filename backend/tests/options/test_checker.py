"""Tests for ExpirationChecker."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from src.models.position import AssetType, PutCall


@pytest.fixture
def mock_position():
    """Create a mock option position."""
    pos = MagicMock()
    pos.id = 123
    pos.symbol = "AAPL240119C150"
    pos.asset_type = AssetType.OPTION
    pos.expiry = date.today() + timedelta(days=1)  # Tomorrow
    pos.strike = Decimal("150.00")
    pos.put_call = PutCall.CALL
    pos.quantity = 10
    return pos


@pytest.fixture
def mock_portfolio():
    """Create a mock PortfolioManager."""
    portfolio = AsyncMock()
    return portfolio


@pytest.fixture
def mock_alert_repo():
    """Create a mock AlertRepository."""
    repo = AsyncMock()
    repo.persist_alert.return_value = (True, "alert-123")  # is_new=True
    return repo


class TestExpirationChecker:
    """Tests for ExpirationChecker class."""

    @pytest.mark.asyncio
    async def test_check_expirations_creates_alerts(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should create alerts for positions within threshold."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_checked"] == 1
        assert stats["alerts_created"] >= 1  # At least 1 threshold triggered
        assert mock_alert_repo.persist_alert.called

    @pytest.mark.asyncio
    async def test_check_expirations_deduplicates(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should count deduplicated alerts correctly."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]
        mock_alert_repo.persist_alert.return_value = (False, "alert-123")  # is_new=False

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["alerts_created"] == 0
        assert stats["alerts_deduplicated"] >= 1

    @pytest.mark.asyncio
    async def test_check_expirations_skips_missing_expiry(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip positions without expiry date."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = None
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_skipped_missing_expiry"] == 1
        assert "missing expiry" in stats["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_check_expirations_skips_expired(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip already expired positions."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = date.today() - timedelta(days=1)  # Yesterday
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_already_expired"] == 1
        assert stats["alerts_created"] == 0

    @pytest.mark.asyncio
    async def test_check_expirations_skips_out_of_scope(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip positions outside threshold range (DTE > 7)."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = date.today() + timedelta(days=30)  # 30 days out
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_not_expiring_soon"] == 1
        assert stats["alerts_created"] == 0

    @pytest.mark.asyncio
    async def test_check_expirations_filters_options_only(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should only process OPTION positions."""
        from src.options.checker import ExpirationChecker

        stock_position = MagicMock()
        stock_position.asset_type = AssetType.STOCK

        mock_portfolio.get_positions.return_value = [stock_position, mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        # Only the option should be checked
        assert stats["positions_checked"] == 1

    @pytest.mark.asyncio
    async def test_check_expirations_returns_run_id(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Stats should include run_id for traceability."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert "run_id" in stats
        assert len(stats["run_id"]) > 0


class TestDTECalculation:
    """Tests for DTE (days to expiry) calculation."""

    @pytest.mark.asyncio
    async def test_dte_uses_market_timezone(self, mock_portfolio, mock_alert_repo, mock_position):
        """DTE should be calculated using market timezone."""
        from src.options.checker import ExpirationChecker

        # Set position to expire "today" in NY timezone
        ny_tz = ZoneInfo("America/New_York")
        ny_today = datetime.now(ny_tz).date()
        mock_position.expiry = ny_today
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # Should trigger all 4 thresholds (DTE=0)
        # Since this is DTE=0, all 4 thresholds apply
        assert stats["alerts_attempted"] == 4
