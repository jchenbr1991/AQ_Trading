# Research: Minimal Runnable Trading System

**Feature**: 002-minimal-mvp-trading
**Date**: 2026-02-01

## Research Questions

### Q1: How do strategies receive market data?

**Decision**: Use existing `on_market_data(data: MarketData, context: StrategyContext)` interface

**Findings**:
- Strategies receive `MarketData` with `symbol`, `price` (bar close), `volume`, `timestamp`
- `StrategyContext` provides read-only access to positions and portfolio state
- Strategies return `list[Signal]` with buy/sell actions

**Source**: `backend/src/strategies/base.py:52-65`

### Q2: How to prevent lookahead bias in indicators?

**Decision**: Use `warmup_bars` property + strict event ordering

**Findings**:
- Every strategy declares `warmup_bars` property for minimum history needed
- BacktestEngine processes bars chronologically: signal at bar[i] executes at bar[i+1].open
- RULE: When processing bar[i], NEVER read bar[i+1]
- BacktestEngine loads extra data (3x warmup_bars + 7 days) for warm-up period

**Source**: `backend/src/backtest/engine.py:24-33, 105-174`

### Q3: How to track indicator state across bars?

**Decision**: Use `defaultdict(list)` for per-symbol price/indicator buffers

**Findings**:
- Store indicator state in instance variables keyed by symbol
- Maintain fixed-size windows: `if len(history) > lookback: history.pop(0)`
- Check warmup: `if len(history) < lookback: return []`

**Source**: `backend/src/strategies/examples/momentum.py:36-65`

**Example Pattern**:
```python
def __init__(self):
    self._price_history: dict[str, list[Decimal]] = defaultdict(list)

async def on_market_data(self, data, context):
    history = self._price_history[data.symbol]
    history.append(data.price)
    if len(history) > self.lookback:
        history.pop(0)
    if len(history) < self.lookback:
        return []  # Still warming up
    # Calculate indicator...
```

### Q4: What data is available in each bar?

**Decision**: Use OHLCV from `Bar` dataclass

**Findings**:
- `Bar` contains: `symbol`, `timestamp`, `open`, `high`, `low`, `close`, `volume`
- `timestamp` marks the END of the bar interval (bar close time)
- Currently only daily bars (`interval="1d"`) are supported

**Source**: `backend/src/backtest/models.py:15-45`

### Q5: How should factors compose multiple indicators?

**Decision**: Weighted linear combination with configurable weights

**Findings**:
- No existing factor framework in codebase - this is new
- Follow spec formulas:
  - `momentum_factor = w1 * roc_20 + w2 * price_vs_ma_20`
  - `breakout_factor = w3 * price_vs_high_20 + w4 * volume_zscore`
  - `composite = w_mom * momentum_factor + w_brk * breakout_factor`
- Weights should be configurable parameters (YAML config)

**Design Decision**: Create `factors/` module with `BaseFactor` class that:
- Takes indicator values as input
- Applies configurable weights
- Returns normalized factor score

### Q6: How should PnL attribution work?

**Decision**: Track factor scores at entry, attribute proportionally to weights

**Findings**:
- No existing attribution in codebase - this is new
- Spec formula: `Attribution = factor_weight × factor_score_at_entry × trade_pnl`
- Need to store factor scores in Trade record

**Design Decision**:
- Extend Signal or Trade to include `factor_scores: dict[str, float]`
- Calculate attribution when trade closes
- Attribution sums to total PnL (SC-003: < 0.1% rounding error)

### Q7: How should universe be configured?

**Decision**: Simple YAML configuration file

**Findings**:
- Spec requires hardcoded universe (MU, GLD, GOOG) - FR-001
- No need for database storage for MVP
- YAML is human-readable and easy to modify

**Design Decision**:
```yaml
# config/universe.yaml
universe:
  name: mvp-universe
  symbols:
    - MU
    - GLD
    - GOOG
```

## Alternatives Considered

### Indicator Library Options

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| pandas-ta | Rich indicator library | External dependency | Rejected - custom implementation simpler for MVP |
| ta-lib | Battle-tested, fast | C dependency, complex install | Rejected - overkill for 5 indicators |
| Custom numpy | No dependencies, transparent | Must implement ourselves | **Chosen** - full control, easier debugging |

### Factor Storage Options

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Separate Factor table | Normalized, queryable | Extra DB complexity | Rejected - overkill for MVP |
| JSON in Trade record | Simple, self-contained | Not queryable | **Chosen** - sufficient for attribution |
| Redis cache | Fast reads | Volatile, extra component | Rejected - unnecessary |

### Attribution Calculation Timing

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| Real-time during backtest | Immediate results | Slower backtest | Rejected |
| Post-backtest batch | Clean separation | Extra pass over data | Rejected |
| At trade close | Natural point, single pass | In execution path | **Chosen** - simplest |

## Resolved Unknowns

All technical context items are now resolved:

- ✅ Indicator calculation patterns understood
- ✅ Factor composition design decided
- ✅ PnL attribution approach defined
- ✅ Universe configuration format chosen
- ✅ No lookahead bias patterns verified

## Next Steps

Proceed to Phase 1:
1. Create data-model.md with entity definitions
2. Create API contracts for backtest with attribution
3. Create quickstart.md for developer onboarding
