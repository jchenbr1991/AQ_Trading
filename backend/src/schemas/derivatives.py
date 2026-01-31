# backend/src/schemas/derivatives.py
"""Pydantic response schemas for Derivatives API endpoints.

These schemas support the expiration API routes for derivative lifecycle management.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from src.models.derivative_contract import ContractType, PutCall


class ExpirationAlertResponse(BaseModel):
    """Response schema for a derivative expiration alert.

    Attributes:
        symbol: The derivative contract symbol (e.g., AAPL240119C00150000)
        underlying: The underlying asset symbol (e.g., AAPL)
        expiry: The expiration date
        days_to_expiry: Number of days until expiration
        contract_type: Type of contract (option or future)
        put_call: For options, whether it's a put or call (None for futures)
        strike: For options, the strike price (None for futures)
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    underlying: str
    expiry: date
    days_to_expiry: int
    contract_type: ContractType
    put_call: PutCall | None
    strike: Decimal | None


class ExpiringPositionsResponse(BaseModel):
    """Response schema for listing expiring positions.

    Attributes:
        positions: List of positions expiring within the requested window
        total: Total number of expiring positions
        warning_days: The days window used for the query
    """

    model_config = ConfigDict(from_attributes=True)

    positions: list[ExpirationAlertResponse]
    total: int
    warning_days: int


class RollPlanResponse(BaseModel):
    """Response schema for a futures roll plan.

    Attributes:
        symbol: The current position symbol (e.g., ESH24)
        strategy: The roll strategy being applied (calendar_spread or close_open)
        close_action: Description of the close action (e.g., "SELL ESH24 to close")
        open_action: Description of the open action for calendar spreads,
                    None for CLOSE_OPEN strategy
    """

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    strategy: str
    close_action: str
    open_action: str | None


class RollPlanErrorResponse(BaseModel):
    """Response schema for roll plan errors.

    Attributes:
        detail: Error message describing why the roll plan could not be generated
        symbol: The symbol that was requested
    """

    detail: str
    symbol: str
