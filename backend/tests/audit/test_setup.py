"""Tests for audit setup module.

TDD: Write tests FIRST, then implement setup.py to make them pass.
"""

from unittest.mock import MagicMock, patch

from src.audit.service import AuditService


class TestInitAuditService:
    """Tests for init_audit_service() function."""

    def test_init_audit_service_creates_repository_with_session(self):
        """init_audit_service should create repository with the provided session."""
        from src.audit.setup import init_audit_service

        mock_session = MagicMock()

        with patch("src.audit.setup.AuditRepository") as MockRepo:
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = MagicMock()

                init_audit_service(mock_session)

                MockRepo.assert_called_once_with(mock_session)

    def test_init_audit_service_creates_service_with_repository(self):
        """init_audit_service should create service with the repository."""
        from src.audit.setup import init_audit_service

        mock_session = MagicMock()
        mock_repo = MagicMock()

        with patch("src.audit.setup.AuditRepository") as MockRepo:
            MockRepo.return_value = mock_repo
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = MagicMock()

                init_audit_service(mock_session)

                MockService.assert_called_once_with(repository=mock_repo)

    def test_init_audit_service_returns_service(self):
        """init_audit_service should return the created AuditService."""
        from src.audit.setup import init_audit_service

        mock_session = MagicMock()
        mock_service = MagicMock()

        with patch("src.audit.setup.AuditRepository"):
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = mock_service

                result = init_audit_service(mock_session)

                assert result is mock_service

    def test_init_audit_service_stores_global_instance(self):
        """init_audit_service should store service in global instance."""
        from src.audit import setup
        from src.audit.setup import init_audit_service

        mock_session = MagicMock()
        mock_service = MagicMock()

        with patch("src.audit.setup.AuditRepository"):
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = mock_service

                init_audit_service(mock_session)

                assert setup._audit_service is mock_service

    def test_init_audit_service_replaces_existing_instance(self):
        """init_audit_service should replace any existing global instance."""
        from src.audit import setup
        from src.audit.setup import init_audit_service

        mock_session1 = MagicMock()
        mock_session2 = MagicMock()
        mock_service1 = MagicMock()
        mock_service2 = MagicMock()

        with patch("src.audit.setup.AuditRepository"):
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = mock_service1
                init_audit_service(mock_session1)
                assert setup._audit_service is mock_service1

                MockService.return_value = mock_service2
                init_audit_service(mock_session2)
                assert setup._audit_service is mock_service2


class TestGetAuditService:
    """Tests for get_audit_service() function."""

    def test_get_audit_service_returns_none_when_not_initialized(self):
        """get_audit_service should return None if not initialized."""
        from src.audit import setup
        from src.audit.setup import get_audit_service

        # Reset global state
        setup._audit_service = None

        result = get_audit_service()

        assert result is None

    def test_get_audit_service_returns_service_after_init(self):
        """get_audit_service should return the service after initialization."""
        from src.audit.setup import get_audit_service, init_audit_service

        mock_session = MagicMock()
        mock_service = MagicMock()

        with patch("src.audit.setup.AuditRepository"):
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = mock_service

                init_audit_service(mock_session)
                result = get_audit_service()

                assert result is mock_service

    def test_get_audit_service_returns_same_instance(self):
        """get_audit_service should return the same instance on multiple calls."""
        from src.audit.setup import get_audit_service, init_audit_service

        mock_session = MagicMock()
        mock_service = MagicMock()

        with patch("src.audit.setup.AuditRepository"):
            with patch("src.audit.setup.AuditService") as MockService:
                MockService.return_value = mock_service

                init_audit_service(mock_session)
                result1 = get_audit_service()
                result2 = get_audit_service()

                assert result1 is result2


class TestSetupModuleDocstring:
    """Tests for module docstring and integration examples."""

    def test_module_has_docstring(self):
        """setup module should have a docstring."""
        from src.audit import setup

        assert setup.__doc__ is not None
        assert len(setup.__doc__) > 0

    def test_docstring_mentions_usage(self):
        """setup module docstring should mention usage."""
        from src.audit import setup

        assert "init_audit_service" in setup.__doc__
        assert "get_audit_service" in setup.__doc__


class TestSetupIntegration:
    """Integration tests for setup module."""

    def test_init_creates_real_instances(self):
        """init_audit_service should create real instances when not mocked."""
        from src.audit.setup import init_audit_service

        mock_session = MagicMock()

        service = init_audit_service(mock_session)

        assert isinstance(service, AuditService)

    def test_full_init_and_get_flow(self):
        """Test full initialization and getter flow."""
        from src.audit import setup
        from src.audit.setup import get_audit_service, init_audit_service

        # Reset state
        setup._audit_service = None

        mock_session = MagicMock()

        # Before init
        assert get_audit_service() is None

        # After init
        service = init_audit_service(mock_session)
        assert get_audit_service() is service
        assert isinstance(service, AuditService)
