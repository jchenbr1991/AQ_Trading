"""Performance metrics calculator for backtest results."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from src.backtest.models import Trade


class MetricsCalculator:
    """Computes performance metrics from equity curve and trades."""

    @staticmethod
    def compute(
        equity_curve: list[tuple[datetime, Decimal]],
        trades: list[Trade],
        initial_capital: Decimal,
        entry_prices: dict[str, Decimal] | None = None,
    ) -> dict[str, Any]:
        """Compute all summary metrics.

        Args:
            equity_curve: Time series of (timestamp, equity) tuples.
            trades: List of all executed trades during the backtest.
            initial_capital: Starting cash amount for the backtest.
            entry_prices: Optional dict mapping symbol to entry price for PnL calculation.

        Returns:
            Dict with:
              - total_return: (final - initial) / initial
              - annualized_return: (1 + total_return) ^ (252/trading_days) - 1
              - sharpe_ratio: mean(daily_returns) / std(daily_returns) * sqrt(252), or 0 if std=0 or len<2
              - max_drawdown: max peak-to-trough decline
              - win_rate: profitable_sells / total_sells (or 0 if no sells)
              - total_trades: len(trades)
              - avg_trade_pnl: sum(trade_pnls) / total_sells (or 0 if no sells)
        """
        total_return = MetricsCalculator._compute_total_return(equity_curve, initial_capital)
        trading_days = len(equity_curve) - 1 if len(equity_curve) > 1 else 0
        annualized_return = MetricsCalculator._compute_annualized_return(total_return, trading_days)
        sharpe_ratio = MetricsCalculator._compute_sharpe_ratio(equity_curve)
        max_drawdown = MetricsCalculator._compute_max_drawdown(equity_curve)
        win_rate, avg_trade_pnl = MetricsCalculator._compute_trade_metrics(trades, entry_prices)

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(trades),
            "avg_trade_pnl": avg_trade_pnl,
        }

    @staticmethod
    def _compute_total_return(
        equity_curve: list[tuple[datetime, Decimal]],
        initial_capital: Decimal,
    ) -> Decimal:
        """Compute total return as (final - initial) / initial."""
        if not equity_curve or initial_capital == 0:
            return Decimal("0")

        final_equity = equity_curve[-1][1]
        return (final_equity - initial_capital) / initial_capital

    @staticmethod
    def _compute_annualized_return(
        total_return: Decimal,
        trading_days: int,
    ) -> Decimal:
        """Compute annualized return: (1 + total_return) ^ (252/trading_days) - 1."""
        if trading_days <= 0:
            return Decimal("0")

        # Use float for exponentiation, then convert back to Decimal
        total_return_float = float(total_return)
        exponent = 252 / trading_days
        annualized = (1 + total_return_float) ** exponent - 1

        # Round to reasonable precision to avoid floating point artifacts
        return Decimal(str(round(annualized, 10)))

    @staticmethod
    def _compute_sharpe_ratio(
        equity_curve: list[tuple[datetime, Decimal]],
    ) -> Decimal:
        """Compute Sharpe ratio: mean(daily_returns) / std(daily_returns) * sqrt(252).

        Returns 0 if std(returns) == 0 or len(equity_curve) < 2.
        """
        if len(equity_curve) < 2:
            return Decimal("0")

        # Compute daily returns
        daily_returns: list[float] = []
        for i in range(1, len(equity_curve)):
            prev_equity = float(equity_curve[i - 1][1])
            curr_equity = float(equity_curve[i][1])
            if prev_equity != 0:
                daily_return = (curr_equity - prev_equity) / prev_equity
                daily_returns.append(daily_return)

        if len(daily_returns) < 1:
            return Decimal("0")

        # Compute mean
        mean_return = sum(daily_returns) / len(daily_returns)

        # Compute standard deviation
        if len(daily_returns) < 2:
            return Decimal("0")

        variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_return = variance**0.5

        if std_return == 0:
            return Decimal("0")

        # Annualize: multiply by sqrt(252)
        sharpe = (mean_return / std_return) * (252**0.5)

        return Decimal(str(round(sharpe, 10)))

    @staticmethod
    def _compute_max_drawdown(
        equity_curve: list[tuple[datetime, Decimal]],
    ) -> Decimal:
        """Compute maximum drawdown as the largest peak-to-trough decline."""
        if len(equity_curve) < 2:
            return Decimal("0")

        max_drawdown = Decimal("0")
        peak = equity_curve[0][1]

        for _, equity in equity_curve:
            if equity > peak:
                peak = equity
            elif peak > 0:
                drawdown = (peak - equity) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        return max_drawdown

    @staticmethod
    def _compute_trade_metrics(
        trades: list[Trade],
        entry_prices: dict[str, Decimal] | None = None,
    ) -> tuple[Decimal, Decimal]:
        """Compute win rate and average trade PnL from trades.

        Win rate is based on sell trades only. A trade is a winner if
        the sell price is higher than the entry price (or the preceding buy price).

        Returns:
            Tuple of (win_rate, avg_trade_pnl).
        """
        if not trades:
            return Decimal("0"), Decimal("0")

        # Track entry prices from buy trades
        symbol_entry_prices: dict[str, Decimal] = entry_prices.copy() if entry_prices else {}

        # Find sell trades and compute PnL
        sell_trades: list[Trade] = []
        trade_pnls: list[Decimal] = []
        winners = 0

        for trade in trades:
            if trade.side == "buy":
                # Update entry price for this symbol
                symbol_entry_prices[trade.symbol] = trade.fill_price
            elif trade.side == "sell":
                sell_trades.append(trade)
                entry_price = symbol_entry_prices.get(trade.symbol, Decimal("0"))
                if entry_price > 0:
                    pnl = (trade.fill_price - entry_price) * trade.quantity - trade.commission
                    trade_pnls.append(pnl)
                    if trade.fill_price > entry_price:
                        winners += 1

        total_sells = len(sell_trades)
        if total_sells == 0:
            return Decimal("0"), Decimal("0")

        win_rate = Decimal(str(winners)) / Decimal(str(total_sells))
        avg_pnl = sum(trade_pnls) / Decimal(str(total_sells)) if trade_pnls else Decimal("0")

        return win_rate, avg_pnl
