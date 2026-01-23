# backend/src/core/portfolio.py
from datetime import datetime, date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from src.models import Position, AssetType, PutCall, TransactionAction


@runtime_checkable
class RedisClient(Protocol):
    """Protocol for Redis client interface."""

    async def get(self, key: str) -> str | None:
        ...

    async def set(self, key: str, value: str) -> None:
        ...


class PortfolioManager:
    """
    Core portfolio management service.

    Handles position tracking, fill recording, and P&L calculations.
    """

    def __init__(self, repo, redis: RedisClient | None = None):
        """
        Initialize PortfolioManager.

        Args:
            repo: PortfolioRepository instance for database operations
            redis: Optional Redis client for real-time price data
        """
        self._repo = repo
        self._redis = redis

    async def get_account(self, account_id: str):
        """Get account by ID."""
        return await self._repo.get_account(account_id)

    async def sync_account(
        self,
        account_id: str,
        cash: Decimal,
        buying_power: Decimal,
        margin_used: Decimal,
        total_equity: Decimal,
    ):
        """
        Sync account data from broker.

        Args:
            account_id: Account identifier
            cash: Available cash balance
            buying_power: Available buying power
            margin_used: Margin currently used
            total_equity: Total account equity
        """
        return await self._repo.update_account(
            account_id=account_id,
            cash=cash,
            buying_power=buying_power,
            margin_used=margin_used,
            total_equity=total_equity,
            synced_at=datetime.utcnow(),
        )

    async def get_positions(
        self,
        account_id: str,
        strategy_id: str | None = None,
        symbol: str | None = None,
    ) -> list[Position]:
        """
        Get positions for an account.

        Args:
            account_id: Account identifier
            strategy_id: Optional filter by strategy
            symbol: Optional filter by symbol

        Returns:
            List of Position objects
        """
        return await self._repo.get_positions(
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
        )

    async def get_position(
        self,
        account_id: str,
        symbol: str,
        strategy_id: str | None = None,
    ) -> Position | None:
        """
        Get a specific position.

        Args:
            account_id: Account identifier
            symbol: Symbol to look up
            strategy_id: Optional strategy ID

        Returns:
            Position if found, None otherwise
        """
        return await self._repo.get_position(
            account_id=account_id,
            symbol=symbol,
            strategy_id=strategy_id,
        )

    async def get_exposure(
        self,
        account_id: str,
        symbol: str,
    ) -> Decimal:
        """
        Get total exposure for a symbol across all strategies.

        Args:
            account_id: Account identifier
            symbol: Symbol to calculate exposure for

        Returns:
            Total market value exposure
        """
        positions = await self._repo.get_positions(
            account_id=account_id,
            symbol=symbol,
        )
        return sum(
            pos.market_value for pos in positions
        ) if positions else Decimal("0")

    async def record_fill(
        self,
        account_id: str,
        symbol: str,
        side: str,  # "buy" or "sell"
        quantity: int,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        strategy_id: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        asset_type: AssetType = AssetType.STOCK,
        strike: Decimal | None = None,
        expiry: date | None = None,
        put_call: PutCall | None = None,
    ) -> Position:
        """
        Record a trade fill and update positions.

        This method:
        1. Checks if a position exists for the symbol/strategy
        2. If not, creates a new position
        3. If exists, updates quantity and recalculates avg_cost
        4. If position is fully closed, removes it and calculates realized P&L
        5. Records the transaction

        Args:
            account_id: Account identifier
            symbol: Trading symbol
            side: "buy" or "sell"
            quantity: Number of shares/contracts
            price: Fill price
            commission: Trading commission
            strategy_id: Optional strategy tag
            order_id: Internal order ID
            broker_order_id: Broker's order ID
            asset_type: Type of asset (stock, option, future)
            strike: Strike price for options
            expiry: Expiry date for options
            put_call: Put or call for options

        Returns:
            The created or updated Position
        """
        existing = await self._repo.get_position(
            account_id=account_id,
            symbol=symbol,
            strategy_id=strategy_id,
        )

        action = TransactionAction.BUY if side == "buy" else TransactionAction.SELL
        realized_pnl = Decimal("0")
        multiplier = 100 if asset_type == AssetType.OPTION else 1

        if existing is None:
            # Opening a new position
            position = await self._repo.create_position(
                account_id=account_id,
                symbol=symbol,
                quantity=quantity if side == "buy" else -quantity,
                avg_cost=price,
                asset_type=asset_type,
                strategy_id=strategy_id,
                strike=strike,
                expiry=expiry,
                put_call=put_call,
            )
        else:
            # Update existing position
            old_qty = existing.quantity
            old_cost = existing.avg_cost

            if side == "buy":
                new_qty = old_qty + quantity
                if new_qty == 0:
                    # Closing short position
                    realized_pnl = (old_cost - price) * quantity * multiplier
                    await self._repo.close_position(
                        account_id=account_id,
                        symbol=symbol,
                        strategy_id=strategy_id,
                    )
                    # Return a dummy position for closed state
                    position = existing
                    position.quantity = 0
                elif old_qty < 0:
                    # Covering short: P&L on covered portion
                    cover_qty = min(quantity, abs(old_qty))
                    realized_pnl = (old_cost - price) * cover_qty * multiplier
                    if new_qty > 0:
                        # Flipped from short to long
                        new_cost = price
                    else:
                        # Still short
                        new_cost = old_cost
                    position = await self._repo.update_position(
                        account_id=account_id,
                        symbol=symbol,
                        quantity=new_qty,
                        avg_cost=new_cost,
                        strategy_id=strategy_id,
                    )
                else:
                    # Adding to long position - calculate weighted avg cost
                    total_cost = (old_cost * old_qty) + (price * quantity)
                    new_cost = total_cost / new_qty
                    position = await self._repo.update_position(
                        account_id=account_id,
                        symbol=symbol,
                        quantity=new_qty,
                        avg_cost=new_cost,
                        strategy_id=strategy_id,
                    )
            else:  # sell
                new_qty = old_qty - quantity
                if new_qty == 0:
                    # Fully closing long position
                    realized_pnl = (price - old_cost) * quantity * multiplier
                    await self._repo.close_position(
                        account_id=account_id,
                        symbol=symbol,
                        strategy_id=strategy_id,
                    )
                    # Return the position before closing
                    position = existing
                    position.quantity = 0
                elif old_qty > 0:
                    # Partial close or flip to short
                    sell_qty = min(quantity, old_qty)
                    realized_pnl = (price - old_cost) * sell_qty * multiplier
                    if new_qty < 0:
                        # Flipped from long to short
                        new_cost = price
                    else:
                        # Still long, avg cost unchanged
                        new_cost = old_cost
                    position = await self._repo.update_position(
                        account_id=account_id,
                        symbol=symbol,
                        quantity=new_qty,
                        avg_cost=new_cost,
                        strategy_id=strategy_id,
                    )
                else:
                    # Adding to short position
                    total_cost = (old_cost * abs(old_qty)) + (price * quantity)
                    new_cost = total_cost / abs(new_qty)
                    position = await self._repo.update_position(
                        account_id=account_id,
                        symbol=symbol,
                        quantity=new_qty,
                        avg_cost=new_cost,
                        strategy_id=strategy_id,
                    )

        # Record the transaction
        await self._repo.record_transaction(
            account_id=account_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            commission=commission,
            realized_pnl=realized_pnl,
            strategy_id=strategy_id,
            order_id=order_id,
            broker_order_id=broker_order_id,
        )

        return position

    async def calculate_unrealized_pnl(
        self,
        account_id: str,
        strategy_id: str | None = None,
    ) -> Decimal:
        """
        Calculate total unrealized P&L for an account.

        Uses real-time prices from Redis if available,
        otherwise falls back to stored current_price.

        Args:
            account_id: Account identifier
            strategy_id: Optional filter by strategy

        Returns:
            Total unrealized P&L
        """
        positions = await self._repo.get_positions(
            account_id=account_id,
            strategy_id=strategy_id,
        )

        total_pnl = Decimal("0")
        for pos in positions:
            # Try to get real-time price from Redis
            current_price = pos.current_price
            if self._redis:
                redis_price = await self._redis.get(f"quote:{pos.symbol}:price")
                if redis_price:
                    current_price = Decimal(redis_price)

            multiplier = 100 if pos.asset_type == AssetType.OPTION else 1
            pnl = (current_price - pos.avg_cost) * pos.quantity * multiplier
            total_pnl += pnl

        return total_pnl

    async def calculate_realized_pnl(
        self,
        account_id: str,
        strategy_id: str | None = None,
    ) -> Decimal:
        """
        Calculate total realized P&L from transactions.

        Args:
            account_id: Account identifier
            strategy_id: Optional filter by strategy

        Returns:
            Total realized P&L
        """
        transactions = await self._repo.get_transactions(
            account_id=account_id,
            strategy_id=strategy_id,
        )
        return sum(tx.realized_pnl for tx in transactions) if transactions else Decimal("0")

    async def update_prices(
        self,
        account_id: str,
        prices: dict[str, Decimal],
    ) -> None:
        """
        Update current prices for positions.

        Args:
            account_id: Account identifier
            prices: Dict mapping symbol to current price
        """
        positions = await self._repo.get_positions(account_id=account_id)
        for pos in positions:
            if pos.symbol in prices:
                await self._repo.update_position(
                    account_id=account_id,
                    symbol=pos.symbol,
                    current_price=prices[pos.symbol],
                    strategy_id=pos.strategy_id,
                )
