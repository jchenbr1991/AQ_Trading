# backend/src/api/portfolio.py
"""Portfolio API endpoints (Phase 1 - Mock Data).

TODO: Wire these endpoints to real PortfolioManager when database integration is complete.
"""

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel


# Response schemas
class AccountSummaryResponse(BaseModel):
    """Account summary response schema."""

    account_id: str
    cash: float
    buying_power: float
    total_equity: float
    unrealized_pnl: float
    day_pnl: float
    updated_at: datetime


class PositionResponse(BaseModel):
    """Position response schema."""

    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    strategy_id: str | None


# Router
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# Mock data
# TODO: Replace with real PortfolioManager calls when database integration is complete
MOCK_POSITIONS = [
    PositionResponse(
        symbol="AAPL",
        quantity=100,
        avg_cost=150.00,
        current_price=155.00,
        market_value=15500.00,
        unrealized_pnl=500.00,
        strategy_id="momentum_v1",
    ),
    PositionResponse(
        symbol="GOOGL",
        quantity=50,
        avg_cost=140.00,
        current_price=145.50,
        market_value=7275.00,
        unrealized_pnl=275.00,
        strategy_id="mean_reversion_v1",
    ),
    PositionResponse(
        symbol="MSFT",
        quantity=75,
        avg_cost=380.00,
        current_price=385.00,
        market_value=28875.00,
        unrealized_pnl=375.00,
        strategy_id="momentum_v1",
    ),
]


def _get_mock_account_summary(account_id: str) -> AccountSummaryResponse:
    """Generate mock account summary for a given account_id.

    TODO: Replace with real PortfolioManager.get_account() call.

    Args:
        account_id: The account identifier

    Returns:
        Mock account summary data
    """
    total_unrealized_pnl = sum(p.unrealized_pnl for p in MOCK_POSITIONS)
    total_market_value = sum(p.market_value for p in MOCK_POSITIONS)

    return AccountSummaryResponse(
        account_id=account_id,
        cash=25000.00,
        buying_power=50000.00,
        total_equity=25000.00 + total_market_value,
        unrealized_pnl=total_unrealized_pnl,
        day_pnl=500.00,
        updated_at=datetime.now(timezone.utc),
    )


def _get_mock_positions(account_id: str) -> list[PositionResponse]:
    """Get mock positions for a given account_id.

    TODO: Replace with real PortfolioManager.get_positions() call.

    Args:
        account_id: The account identifier

    Returns:
        List of mock positions
    """
    return MOCK_POSITIONS


@router.get("/account/{account_id}", response_model=AccountSummaryResponse)
async def get_account_summary(account_id: str) -> AccountSummaryResponse:
    """Get account summary for a given account.

    Returns cash balance, buying power, total equity, and P&L information.

    TODO: Wire to real PortfolioManager when database integration is complete.

    Args:
        account_id: The account identifier

    Returns:
        Account summary with financial metrics
    """
    return _get_mock_account_summary(account_id)


@router.get("/positions/{account_id}", response_model=list[PositionResponse])
async def get_positions(account_id: str) -> list[PositionResponse]:
    """Get all positions for a given account.

    Returns list of open positions with current prices and P&L.

    TODO: Wire to real PortfolioManager when database integration is complete.

    Args:
        account_id: The account identifier

    Returns:
        List of positions
    """
    return _get_mock_positions(account_id)
