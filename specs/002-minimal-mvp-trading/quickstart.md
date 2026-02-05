# Quickstart: Minimal Runnable Trading System

**Feature**: 002-minimal-mvp-trading
**Date**: 2026-02-02

## Overview

This guide helps developers run the TrendBreakout strategy through backtest, paper, and live trading modes.

## Prerequisites

- Python 3.11+
- PostgreSQL with TimescaleDB (optional for MVP)
- Redis (optional for MVP)
- Historical OHLCV data (CSV format)

## Installation

```bash
# Navigate to backend directory
cd backend

# Install dependencies
pip install -e ".[dev]"

# Verify installation
python -c "from src.strategies.examples.trend_breakout import TrendBreakoutStrategy; print('OK')"
```

## 1. Configuration

### Universe Configuration

The universe configuration is at `backend/config/universe.yaml`:

```yaml
universe:
  name: mvp-universe
  symbols:
    - MU
    - GLD
    - GOOG
  active: true
```

### Strategy Configuration

The strategy configuration is at `backend/config/strategies/trend_breakout.yaml`:

```yaml
strategy:
  name: trend-breakout-mvp
  class: src.strategies.examples.trend_breakout.TrendBreakoutStrategy
  universe: mvp-universe

  # Thresholds (FR-014)
  entry_threshold: 0.0
  exit_threshold: -0.02

  # Position sizing (FR-015/FR-016)
  position_sizing: equal_weight
  position_size: 100

  # Feature weights (for indicators)
  feature_weights:
    roc_20: 0.5
    price_vs_ma_20: 0.5
    price_vs_high_20: 0.5
    volume_zscore: 0.5

  # Factor weights (for composite)
  factor_weights:
    momentum_factor: 0.5
    breakout_factor: 0.5
```

## 2. Prepare Historical Data

Place CSV files in `backend/data/`. The existing `bars.csv` contains data for AAPL, GOOGL, MSFT, SPY, TSLA.

### CSV Format

The CSV must have this header and format:

```csv
timestamp,symbol,open,high,low,close,volume
2023-01-03T05:00:00+00:00,AAPL,128.34,128.95,122.32,123.21,112117500
2023-01-04T05:00:00+00:00,AAPL,125.00,126.75,123.22,124.48,89113600
```

**Requirements:**
- Timestamp: ISO 8601 format with timezone
- Prices: Decimal values
- Volume: Integer
- Sorted by timestamp ascending

## 3. Run Backtest

### Via Python Script

Create a file `run_backtest.py` in the backend directory:

```python
import asyncio
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig

async def run_backtest():
    # Setup
    data_path = Path("data/bars.csv")
    loader = CSVBarLoader(data_path)
    engine = BacktestEngine(loader)

    # Configure backtest
    config = BacktestConfig(
        strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
        strategy_params={
            "name": "trend-breakout-test",
            "symbols": ["AAPL"],
            "entry_threshold": 0.0,
            "exit_threshold": -0.02,
            "position_sizing": "equal_weight",
            "position_size": 100,
        },
        symbol="AAPL",
        start_date=date(2023, 2, 1),  # After warmup data
        end_date=date(2024, 1, 31),
        initial_capital=Decimal("100000"),
        slippage_bps=5,
        commission_per_share=Decimal("0.005"),
    )

    # Run backtest
    result = await engine.run(config)

    # Display results
    print(f"\n{'='*60}")
    print("Backtest Results")
    print(f"{'='*60}")
    print(f"Total Return: {result.total_return:.2%}")
    print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {result.max_drawdown:.2%}")
    print(f"Win Rate: {result.win_rate:.2%}")
    print(f"Total Trades: {result.total_trades}")
    print(f"Average Trade PnL: ${result.avg_trade_pnl:.2f}")
    print(f"Final Equity: ${result.final_equity:.2f}")

    # Display attribution summary (FR-023)
    if result.attribution_summary:
        print(f"\n{'='*60}")
        print("Factor Attribution Summary")
        print(f"{'='*60}")
        for factor, pnl in result.attribution_summary.items():
            print(f"  {factor}: ${pnl:.2f}")

    return result

if __name__ == "__main__":
    asyncio.run(run_backtest())
```

Run it:

```bash
cd backend
python run_backtest.py
```

### Running Tests

```bash
# Run all backtest tests
cd backend
pytest tests/backtest/ -v

# Run performance tests (SC-004)
pytest tests/performance/test_backtest_timing.py -v

# Run strategy tests
pytest tests/strategies/test_trend_breakout.py -v
```

## 4. Run Paper Trading

### Start Paper Mode

```bash
# Set environment
export TRADING_MODE=paper

# Start backend API server
cd backend
uvicorn src.main:app --reload --port 8000
```

### Paper Trading Script

Create `run_paper.py`:

```python
import asyncio
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.strategies.examples.trend_breakout import TrendBreakoutStrategy
from src.strategies.base import MarketData
from src.broker.paper_broker import PaperBroker

async def run_paper_simulation():
    # Initialize strategy
    strategy = TrendBreakoutStrategy(
        name="trend-breakout-paper",
        symbols=["AAPL"],
        entry_threshold=0.0,
        exit_threshold=-0.02,
        position_sizing="equal_weight",
        position_size=100,
    )

    # Initialize paper broker
    broker = PaperBroker(fill_delay=0.0, slippage_bps=5)

    await strategy.on_start()

    # Simulate market data (in real paper mode, this comes from live feed)
    # For testing, we create simulated market data
    current_position_qty = 0

    sample_prices = [150.00, 151.50, 153.00, 154.25, 152.00, 149.50]

    for i, price in enumerate(sample_prices):
        # Create mock context
        context = MagicMock()
        if current_position_qty > 0:
            class MockPosition:
                quantity = current_position_qty
                avg_cost = Decimal("150.00")
            async def get_pos(sym): return MockPosition()
            context.get_position = get_pos
        else:
            async def get_pos(sym): return None
            context.get_position = get_pos

        # Create market data
        market_data = MarketData(
            symbol="AAPL",
            price=Decimal(str(price)),
            bid=Decimal(str(price - 0.01)),
            ask=Decimal(str(price + 0.01)),
            volume=1000000,
            timestamp=datetime.now(timezone.utc),
        )

        # Process through strategy
        signals = await strategy.on_market_data(market_data, context)

        for signal in signals:
            print(f"Signal: {signal.action} {signal.quantity} {signal.symbol}")
            if signal.action == "buy":
                current_position_qty += signal.quantity
            elif signal.action == "sell":
                current_position_qty -= signal.quantity

    await strategy.on_stop()
    print(f"\nFinal position: {current_position_qty}")

if __name__ == "__main__":
    asyncio.run(run_paper_simulation())
```

## 5. Run Live Trading

**WARNING**: Live trading involves real money. Ensure thorough testing first.

### Prerequisites
- Broker API configured (e.g., Futu OpenAPI)
- Risk limits configured in `config/strategies/trend_breakout.yaml`
- Paper trading validated

### Enable Live Mode

```bash
# Set environment
export TRADING_MODE=live
export FUTU_HOST=127.0.0.1
export FUTU_PORT=11111

# Start backend with live mode
cd backend
uvicorn src.main:app --port 8000
```

### Safety Features (T045)

Live mode includes these safety features:
- `enabled: false` by default - must be explicitly enabled
- `require_broker_connection: true` - verifies broker connection before trading
- `require_confirmation: true` - requires confirmation for orders
- Risk limits: max_position_size, max_order_value, max_daily_loss

## 6. View Attribution Report

### After Backtest

```python
# Get attribution by trade
for trade in result.trades:
    if trade.attribution:
        print(f"\n{trade.symbol} - PnL: ${trade.pnl:.2f}")
        pnl_total = sum(trade.attribution.values())
        for factor, attr in trade.attribution.items():
            pct = (attr / pnl_total * 100) if pnl_total != 0 else 0
            print(f"  {factor}: ${attr:.2f} ({pct:.1f}%)")
```

### Attribution Validation (SC-003)

The system automatically validates that attribution sums match PnL within 0.1% tolerance:

```python
from src.backtest.attribution import AttributionCalculator

calc = AttributionCalculator()

# Validate a single trade's attribution
is_valid = calc.validate_attribution(trade.attribution, trade.pnl)
assert is_valid, "Attribution sum must equal PnL within 0.1%"
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/strategies/examples/trend_breakout.py` | TrendBreakout strategy implementation |
| `src/strategies/indicators/` | Technical indicator implementations |
| `src/strategies/factors/` | Factor composition (momentum, breakout) |
| `src/backtest/engine.py` | Backtest engine orchestrator |
| `src/backtest/attribution.py` | PnL attribution calculator (FR-023) |
| `src/backtest/bar_loader.py` | CSV data loader |
| `src/backtest/models.py` | Data models (BacktestConfig, BacktestResult) |
| `src/broker/paper_broker.py` | Paper trading broker |
| `config/universe.yaml` | Trading universe configuration |
| `config/strategies/trend_breakout.yaml` | Strategy parameters |

## Troubleshooting

### "Insufficient warmup data"
- Ensure CSV data starts at least 30 days before backtest start_date
- Strategy needs 20+ bars for indicator warmup (warmup_bars property)
- Example: For start_date=2023-02-01, data should start from 2023-01-01

### "No signals generated"
- Check threshold configuration (entry_threshold, exit_threshold)
- Verify data quality (no gaps, correct format)
- Enable debug logging: `export LOG_LEVEL=DEBUG`
- Ensure enough volatility in price data to trigger signals

### "Attribution doesn't sum to PnL"
- This indicates a bug - attribution should sum to total PnL within 0.1% (SC-003)
- Check factor weight normalization
- Run attribution validation tests: `pytest tests/backtest/test_attribution.py -v`

### "ModuleNotFoundError"
- Ensure you're in the backend directory
- Install package: `pip install -e ".[dev]"`
- Verify Python path includes src directory

## Performance Requirements (SC-004)

The backtest engine must complete:
- 1 year of daily data
- For 3 symbols
- In under 30 seconds

Run performance test:
```bash
pytest tests/performance/test_backtest_timing.py::TestBacktestPerformance::test_backtest_one_year_three_symbols_under_30_seconds -v
```

## Next Steps

1. Review backtest results and factor attribution
2. Tune thresholds based on performance
3. Run extended paper trading (1+ weeks)
4. Validate signal consistency between modes (SC-002)
5. Gradually increase position sizes
6. Monitor live trading with kill switch ready (T045)
