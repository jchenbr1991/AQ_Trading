# backend/tests/api/test_reconciliation_api.py
"""Tests for Reconciliation API endpoints."""


class TestGetRecentAlerts:
    """Tests for GET /api/reconciliation/recent endpoint."""

    async def test_get_recent_alerts_returns_list(self, client):
        """GET /api/reconciliation/recent returns a list of alerts."""
        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_recent_alerts_has_mock_data(self, client):
        """GET /api/reconciliation/recent returns mock alerts for frontend development."""
        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1  # At least one mock alert

    async def test_alert_has_required_fields(self, client):
        """Each alert has all required fields."""
        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        alert = data[0]
        assert "timestamp" in alert
        assert "severity" in alert
        assert "type" in alert
        assert "symbol" in alert
        assert "local_value" in alert
        assert "broker_value" in alert
        assert "message" in alert

    async def test_severity_values_are_valid(self, client):
        """Alert severity values are one of: info, warning, critical."""
        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()

        valid_severities = {"info", "warning", "critical"}
        for alert in data:
            assert alert["severity"] in valid_severities


class TestAddAlert:
    """Tests for add_alert functionality."""

    async def test_add_alert_appears_in_recent(self, client):
        """Added alerts appear in GET /api/reconciliation/recent."""
        from src.api.reconciliation import add_alert, clear_alerts

        clear_alerts()

        add_alert(
            severity="critical",
            alert_type="MISSING_LOCAL",
            symbol="TSLA",
            local_value=None,
            broker_value="50",
            message="Broker has 50 shares we don't track",
        )

        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["severity"] == "critical"
        assert data[0]["type"] == "MISSING_LOCAL"
        assert data[0]["symbol"] == "TSLA"
        assert data[0]["local_value"] is None
        assert data[0]["broker_value"] == "50"
        assert data[0]["message"] == "Broker has 50 shares we don't track"

    async def test_alerts_limited_to_10(self, client):
        """Only the last 10 alerts are kept."""
        from src.api.reconciliation import add_alert, clear_alerts

        clear_alerts()

        # Add 15 alerts
        for i in range(15):
            add_alert(
                severity="info",
                alert_type="TEST",
                symbol=f"SYM{i}",
                local_value=str(i),
                broker_value=str(i),
                message=f"Alert {i}",
            )

        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

        # Should have alerts 5-14 (oldest 5 dropped)
        symbols = [alert["symbol"] for alert in data]
        assert "SYM5" in symbols
        assert "SYM14" in symbols
        assert "SYM0" not in symbols

    async def test_alerts_ordered_newest_first(self, client):
        """Alerts are returned with newest first."""
        from src.api.reconciliation import add_alert, clear_alerts

        clear_alerts()

        add_alert(
            severity="info",
            alert_type="TEST",
            symbol="FIRST",
            local_value=None,
            broker_value=None,
            message="First alert",
        )
        add_alert(
            severity="info",
            alert_type="TEST",
            symbol="SECOND",
            local_value=None,
            broker_value=None,
            message="Second alert",
        )

        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["symbol"] == "SECOND"  # Newest first
        assert data[1]["symbol"] == "FIRST"


class TestClearAlerts:
    """Tests for clear_alerts functionality."""

    async def test_clear_alerts_removes_all(self, client):
        """clear_alerts removes all alerts."""
        from src.api.reconciliation import add_alert, clear_alerts

        add_alert(
            severity="info",
            alert_type="TEST",
            symbol="TEST",
            local_value=None,
            broker_value=None,
            message="Test",
        )

        clear_alerts()

        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


class TestAlertIsolation:
    """Tests for alert isolation between tests."""

    async def test_alerts_reset_between_tests(self, client):
        """Each test starts with fresh mock alerts."""
        response = await client.get("/api/reconciliation/recent")

        assert response.status_code == 200
        # Should have the default mock alerts
        data = response.json()
        assert len(data) >= 1
