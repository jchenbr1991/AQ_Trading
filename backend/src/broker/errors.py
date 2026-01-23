# backend/src/broker/errors.py
"""Broker error types."""


class BrokerError(Exception):
    """Base exception for broker errors."""
    pass


class OrderSubmissionError(BrokerError):
    """Error submitting order to broker."""

    def __init__(self, message: str, order_id: str = None, symbol: str = None):
        super().__init__(message)
        self.order_id = order_id
        self.symbol = symbol


class OrderCancelError(BrokerError):
    """Error cancelling order."""

    def __init__(self, message: str, broker_order_id: str = None):
        super().__init__(message)
        self.broker_order_id = broker_order_id
