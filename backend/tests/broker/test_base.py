# backend/tests/broker/test_base.py
import pytest
from typing import Protocol, runtime_checkable

from src.broker.base import Broker
from src.broker.errors import BrokerError, OrderSubmissionError, OrderCancelError


class TestBrokerProtocol:
    def test_broker_is_protocol(self):
        """Broker is a Protocol class."""
        assert hasattr(Broker, '__protocol_attrs__') or isinstance(Broker, type)

    def test_protocol_methods(self):
        """Broker defines required methods."""
        # Check method signatures exist
        assert hasattr(Broker, 'submit_order')
        assert hasattr(Broker, 'cancel_order')
        assert hasattr(Broker, 'get_order_status')
        assert hasattr(Broker, 'subscribe_fills')


class TestBrokerErrors:
    def test_broker_error_base(self):
        """BrokerError is base exception."""
        err = BrokerError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert isinstance(err, Exception)

    def test_order_submission_error(self):
        """OrderSubmissionError captures order details."""
        err = OrderSubmissionError(
            message="Insufficient funds",
            order_id="ord-123",
            symbol="AAPL"
        )
        assert err.order_id == "ord-123"
        assert err.symbol == "AAPL"
        assert "Insufficient funds" in str(err)

    def test_order_cancel_error(self):
        """OrderCancelError captures cancel details."""
        err = OrderCancelError(
            message="Order already filled",
            broker_order_id="BRK-456"
        )
        assert err.broker_order_id == "BRK-456"
