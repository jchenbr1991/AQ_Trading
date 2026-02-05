# Data Model: Minimal Runnable Trading System

**Feature**: 002-minimal-mvp-trading
**Date**: 2026-02-01

## Entity Overview

```
Universe ──┬── Symbol
           │
Feature ───┼── IndicatorValue (per symbol, per bar)
           │
Factor ────┼── FactorScore (per symbol, per bar)
           │
Strategy ──┼── Signal ──► Trade ──► Attribution
```

## Entities

### Universe

A collection of tradeable symbols for the strategy.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | string | Universe identifier | Required, unique |
| symbols | list[string] | List of ticker symbols | Non-empty |
| active | bool | Whether universe is enabled | Default: true |

**Source**: Configuration file (YAML)

**Example**:
```yaml
universe:
  name: mvp-universe
  symbols: [MU, GLD, GOOG]
  active: true
```

---

### Feature (Indicator)

A calculated technical indicator derived from OHLCV data.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | string | Indicator identifier | Required (e.g., "roc_20") |
| symbol | string | Ticker symbol | Required |
| timestamp | datetime | Bar timestamp | Required |
| value | Decimal | Calculated indicator value | Nullable (warmup period) |
| lookback | int | Lookback period in bars | > 0 |

**Implemented Features** (per spec FR-003 to FR-007):

| Name | Formula | Default Lookback |
|------|---------|------------------|
| `roc_n` | `(price[t] - price[t-n]) / price[t-n]` | 5, 20 |
| `price_vs_ma_n` | `(price[t] - SMA[t,n]) / SMA[t,n]` | 20 |
| `price_vs_high_n` | `(price[t] - max(high[t-n:t])) / max(high[t-n:t])` | 20 |
| `volume_zscore` | `(volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])` | 20 |
| `volatility_n` | `std(returns[t-n:t])` | 20 |

**Storage**: In-memory (strategy instance variables)

---

### Factor

A composite signal derived from one or more features.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | string | Factor identifier | Required |
| symbol | string | Ticker symbol | Required |
| timestamp | datetime | Calculation timestamp | Required |
| score | Decimal | Weighted combination of features | Required |
| components | dict[str, Decimal] | Individual feature values | Required |
| weights | dict[str, Decimal] | Feature weights used | Required |

**Implemented Factors** (per spec FR-010 to FR-012):

| Name | Formula | Default Weights |
|------|---------|-----------------|
| `momentum_factor` | `w1 * roc_20 + w2 * price_vs_ma_20` | w1=0.5, w2=0.5 |
| `breakout_factor` | `w3 * price_vs_high_20 + w4 * volume_zscore` | w3=0.5, w4=0.5 |
| `composite` | `w_mom * momentum + w_brk * breakout` | w_mom=0.5, w_brk=0.5 |

**Storage**: In-memory (strategy instance variables)

---

### StrategyConfig

Configuration for TrendBreakoutStrategy.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| name | string | Strategy identifier | Required, unique |
| universe | string | Universe name reference | Required |
| entry_threshold | Decimal | Composite score to trigger buy | Default: 0.0 |
| exit_threshold | Decimal | Composite score to trigger sell | Default: -0.02 |
| position_sizing | enum | "equal_weight" or "fixed_risk" | Default: equal_weight |
| position_size | int | Shares per position (equal_weight) | Default: 100 |
| risk_per_trade | Decimal | Risk % per trade (fixed_risk) | Default: 0.02 |
| feature_weights | dict | Weights for feature → factor | See defaults above |
| factor_weights | dict | Weights for factor → composite | See defaults above |

**Source**: Configuration file (YAML)

---

### Signal (Extended)

Extends existing Signal with factor scores for attribution.

| Field | Type | Description | Existing? |
|-------|------|-------------|-----------|
| strategy_id | string | Strategy identifier | ✓ Existing |
| symbol | string | Ticker symbol | ✓ Existing |
| action | enum | "buy" or "sell" | ✓ Existing |
| quantity | int | Number of shares | ✓ Existing |
| reason | string | Human-readable explanation | ✓ Existing |
| timestamp | datetime | Signal generation time | ✓ Existing |
| **factor_scores** | dict[str, Decimal] | **NEW**: Factor values at signal time | NEW |

**factor_scores Example**:
```python
{
    "momentum_factor": Decimal("0.035"),
    "breakout_factor": Decimal("0.021"),
    "composite": Decimal("0.028")
}
```

---

### Trade (Extended)

Extends existing Trade record with attribution data.

| Field | Type | Description | Existing? |
|-------|------|-------------|-----------|
| id | UUID | Trade identifier | ✓ Existing |
| symbol | string | Ticker symbol | ✓ Existing |
| entry_price | Decimal | Entry fill price | ✓ Existing |
| entry_date | datetime | Entry timestamp | ✓ Existing |
| exit_price | Decimal | Exit fill price | ✓ Existing |
| exit_date | datetime | Exit timestamp | ✓ Existing |
| quantity | int | Position size | ✓ Existing |
| pnl | Decimal | Realized profit/loss | ✓ Existing |
| **entry_factors** | dict[str, Decimal] | **NEW**: Factor scores at entry | NEW |
| **exit_factors** | dict[str, Decimal] | **NEW**: Factor scores at exit | NEW |
| **attribution** | dict[str, Decimal] | **NEW**: PnL attributed to each factor | NEW |

**Attribution Calculation** (per spec FR-023):
```python
# Per FR-023: Attribution = factor_weight × factor_score_at_entry × trade_pnl
# For each factor f:
attribution[f] = factor_weight[f] * entry_factors[f] * pnl

# Note: This formula does not sum to total PnL directly.
# SC-003 requires that the sum of attributions equals total PnL.
# To satisfy both FR-023 and SC-003, normalize after calculation:
total_raw = sum(attribution.values())
if total_raw != 0:
    for f in attribution:
        attribution[f] = attribution[f] * pnl / total_raw
# Constraint: sum(attribution.values()) == pnl (within 0.1% rounding per SC-003)
```

---

### BacktestResult (Extended)

Extends existing BacktestResult with attribution summary.

| Field | Type | Description | Existing? |
|-------|------|-------------|-----------|
| trades | list[Trade] | All completed trades | ✓ Existing |
| metrics | Metrics | Performance metrics | ✓ Existing |
| equity_curve | list[Decimal] | Daily equity values | ✓ Existing |
| **attribution_summary** | dict[str, Decimal] | **NEW**: Total PnL by factor | NEW |

**attribution_summary Example**:
```python
{
    "momentum_factor": Decimal("1234.56"),  # Total PnL from momentum
    "breakout_factor": Decimal("567.89"),   # Total PnL from breakout
    "total": Decimal("1802.45")             # Sum (should match portfolio PnL)
}
```

## State Transitions

### Trade Lifecycle

```
[No Position]
     │
     ▼ Signal(action=buy) at bar[i]
     │
[Pending Entry] ── Fill at bar[i+1].open ──► [Open Position]
                                                   │
                                                   ▼ Signal(action=sell) at bar[j]
                                                   │
                                          [Pending Exit] ── Fill at bar[j+1].open ──► [Closed]
                                                                                           │
                                                                                           ▼
                                                                                   Calculate Attribution
```

### Factor Calculation Flow

```
Bar[t] received
     │
     ▼
Update price/volume history buffers
     │
     ▼
Check warmup (len >= lookback?)
     │
     ├── No ──► Return [] (no signal)
     │
     ▼ Yes
Calculate Features:
  - roc_20, roc_5
  - price_vs_ma_20
  - price_vs_high_20
  - volume_zscore
  - volatility_20
     │
     ▼
Calculate Factors:
  - momentum_factor = w1*roc_20 + w2*price_vs_ma_20
  - breakout_factor = w3*price_vs_high_20 + w4*volume_zscore
  - composite = w_mom*momentum + w_brk*breakout
     │
     ▼
Apply Strategy Logic:
  - composite > entry_threshold AND no position ──► Signal(buy)
  - composite < exit_threshold AND has position ──► Signal(sell)
  - else ──► []
```

## Validation Rules

### Feature Validation
- All features must be calculated with proper lag (FR-008)
- Features must return null during warmup period
- Division by zero: return null if denominator is zero

### Factor Validation
- Factor weights must sum to 1.0 (normalized)
- Factor scores should be bounded (consider clamping to [-1, 1])

### Attribution Validation
- Sum of attribution values must equal trade PnL (< 0.1% error per SC-003)
- All factors present in entry_factors must have attribution entry

## Relationships

```
Universe 1 ──────────────────────► N Symbol
Symbol 1 ────────────────────────► N Feature (per bar)
Symbol 1 ────────────────────────► N Factor (per bar)
Strategy 1 ──────────────────────► 1 Universe
Strategy 1 ──────────────────────► N Signal
Signal 1 ────────────────────────► 1 Trade (if filled)
Trade 1 ─────────────────────────► 1 Attribution
BacktestResult 1 ────────────────► N Trade
BacktestResult 1 ────────────────► 1 AttributionSummary
```
