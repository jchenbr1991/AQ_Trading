"""Tests for options API Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError


class TestExpiringAlertRow:
    """Tests for ExpiringAlertRow model."""

    def test_valid_alert_row(self):
        """Should create valid alert row with all fields."""
        from src.options.models import ExpiringAlertRow

        row = ExpiringAlertRow(
            alert_id="alert-123",
            severity="critical",
            threshold_days=1,
            created_at=datetime.utcnow(),
            acknowledged=False,
            position_id=456,
            symbol="AAPL240119C150",
            strike=150.0,
            put_call="call",
            expiry_date="2024-01-19",
            quantity=10,
            days_to_expiry=1,
            is_closable=True,
        )

        assert row.alert_id == "alert-123"
        assert row.severity == "critical"
        assert row.threshold_days == 1
        assert row.is_closable is True

    def test_optional_fields(self):
        """Should allow optional valuation fields to be None."""
        from src.options.models import ExpiringAlertRow

        row = ExpiringAlertRow(
            alert_id="alert-123",
            severity="warning",
            threshold_days=3,
            created_at=datetime.utcnow(),
            acknowledged=True,
            acknowledged_at=datetime.utcnow(),
            position_id=456,
            symbol="AAPL240119P150",
            strike=150.0,
            put_call="put",
            expiry_date="2024-01-19",
            quantity=-5,
            days_to_expiry=3,
            current_price=2.50,
            market_value=1250.0,
            unrealized_pnl=-250.0,
            is_closable=True,
        )

        assert row.current_price == 2.50
        assert row.market_value == 1250.0

    def test_invalid_severity_rejected(self):
        """Should reject invalid severity values."""
        from src.options.models import ExpiringAlertRow

        with pytest.raises(ValidationError):
            ExpiringAlertRow(
                alert_id="alert-123",
                severity="invalid",  # Not a valid enum value
                threshold_days=1,
                created_at=datetime.utcnow(),
                acknowledged=False,
                position_id=456,
                symbol="AAPL240119C150",
                strike=150.0,
                put_call="call",
                expiry_date="2024-01-19",
                quantity=10,
                days_to_expiry=1,
                is_closable=True,
            )


class TestExpiringAlertsResponse:
    """Tests for ExpiringAlertsResponse model."""

    def test_valid_response(self):
        """Should create valid response with alerts and summary."""
        from src.options.models import AlertSummary, ExpiringAlertsResponse

        response = ExpiringAlertsResponse(
            alerts=[],
            total=0,
            summary=AlertSummary(
                critical_count=0,
                warning_count=0,
                info_count=0,
            ),
        )

        assert response.total == 0
        assert response.summary.critical_count == 0


class TestClosePositionRequest:
    """Tests for ClosePositionRequest model."""

    def test_valid_request(self):
        """Should accept valid close position request."""
        from src.options.models import ClosePositionRequest

        request = ClosePositionRequest(
            reason="expiring_soon",
        )

        assert request.reason == "expiring_soon"

    def test_optional_reason(self):
        """Should allow reason to be optional."""
        from src.options.models import ClosePositionRequest

        request = ClosePositionRequest()
        assert request.reason is None


class TestClosePositionResponse:
    """Tests for ClosePositionResponse model."""

    def test_valid_response(self):
        """Should create valid close position response."""
        from src.options.models import ClosePositionResponse

        response = ClosePositionResponse(
            success=True,
            order_id="order-789",
            message="Close order created",
        )

        assert response.success is True
        assert response.order_id == "order-789"
