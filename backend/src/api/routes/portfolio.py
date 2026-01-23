# backend/src/api/routes/portfolio.py
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.db.repositories.portfolio_repo import PortfolioRepository
from src.core.portfolio import PortfolioManager
from src.schemas import AccountRead, PositionRead, TransactionRead

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


async def get_portfolio_manager(session: AsyncSession = Depends(get_session)):
    repo = PortfolioRepository(session)
    return PortfolioManager(repo=repo, redis=None)  # TODO: inject Redis


@router.get("/accounts/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: str,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    account = await pm.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/accounts/{account_id}/positions", response_model=list[PositionRead])
async def get_positions(
    account_id: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    positions = await pm.get_positions(account_id, strategy_id=strategy_id)
    return positions


@router.get("/accounts/{account_id}/positions/{symbol}", response_model=PositionRead)
async def get_position(
    account_id: str,
    symbol: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    position = await pm.get_position(account_id, symbol, strategy_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.get("/accounts/{account_id}/pnl")
async def get_pnl(
    account_id: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    unrealized = await pm.calculate_unrealized_pnl(account_id, strategy_id)
    realized = await pm.calculate_realized_pnl(account_id, strategy_id)
    return {
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "total_pnl": unrealized + realized,
    }


@router.get("/accounts/{account_id}/exposure/{symbol}")
async def get_exposure(
    account_id: str,
    symbol: str,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    exposure = await pm.get_exposure(account_id, symbol)
    return {"symbol": symbol, "exposure": exposure}
