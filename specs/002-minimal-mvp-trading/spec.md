# Feature Specification: Minimal Runnable Trading System

**Feature Branch**: `002-minimal-mvp-trading`
**Created**: 2026-02-01
**Status**: Draft
**Input**: User description: "Complete backtest → Paper → Live trading loop for MU/GLD/GOOG using Universe + Feature + Factor + Strategy architecture without Hypothesis/Constraints complexity"

> **Context**: This is the **first runnable trading system** on the AQ_Trading platform.
> The infrastructure (Phase 1-3) has been built but not yet exercised end-to-end.
> This feature adds Feature/Factor/Universe layers + the first actual Trading Strategy to bring the system to life.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Backtest on Historical Data (Priority: P1)

As a trader, I want to run a backtest on MU, GLD, and GOOG using the trend/breakout strategy so that I can evaluate the strategy's historical performance before risking real capital.

**Why this priority**: Backtesting is the foundation of strategy validation. Without this, there is no way to assess whether the strategy has merit. This must work first.

**Independent Test**: Can be fully tested by running the backtest engine with historical daily bars and verifying that trades are generated, positions tracked, and performance metrics calculated.

**Acceptance Scenarios**:

1. **Given** historical daily price data for MU, GLD, and GOOG is available, **When** I run a backtest with the trend/breakout strategy, **Then** the system generates a complete trade log with entry/exit dates, prices, and quantities.
2. **Given** a completed backtest run, **When** I request performance metrics, **Then** the system displays total return, Sharpe ratio, max drawdown, and win rate.
3. **Given** factors are calculated during backtest, **When** I request PnL attribution, **Then** the system shows which factor (momentum vs breakout) contributed to each trade's profit or loss.

---

### User Story 2 - Execute Paper Trading (Priority: P2)

As a trader, I want to run the same strategy in paper trading mode so that I can verify the strategy behaves correctly with live market data without risking real money.

**Why this priority**: Paper trading validates that the backtest logic translates correctly to real-time execution. It's the bridge between historical testing and live trading.

**Independent Test**: Can be fully tested by running paper trading for one or more trading sessions, verifying that signals match what backtest would produce for the same data.

**Acceptance Scenarios**:

1. **Given** the paper trading mode is active and market is open, **When** daily bars are received for MU/GLD/GOOG, **Then** the system calculates features and factors using the exact same logic as backtest.
2. **Given** a factor score exceeds the entry threshold, **When** no existing position exists for that symbol, **Then** the system logs a simulated buy order with current price and calculated position size.
3. **Given** a factor score falls below the exit threshold, **When** a position exists for that symbol, **Then** the system logs a simulated sell order and records the paper P&L.

---

### User Story 3 - Execute Live Trading (Priority: P3)

As a trader, I want to execute the same strategy with real orders so that I can generate actual profits using the validated approach.

**Why this priority**: Live trading is the ultimate goal, but it depends on having validated backtest and paper trading first. It carries real financial risk.

**Independent Test**: Can be fully tested by executing one complete trade cycle (entry and exit) on one symbol with minimal position size.

**Acceptance Scenarios**:

1. **Given** live trading mode is active and connected to a broker, **When** the strategy generates a buy signal, **Then** the system submits a real market order through the broker's execution interface.
2. **Given** an open position exists and exit conditions are met, **When** the strategy generates a sell signal, **Then** the system submits a real sell order and records the actual fill price.
3. **Given** any trading session (backtest, paper, or live), **When** comparing the decision logic, **Then** the same factor scores produce the same trading decisions across all three modes.

---

### User Story 4 - View Factor PnL Attribution (Priority: P2)

As a trader, I want to see how each factor contributed to my portfolio's performance so that I can understand what drives returns and refine the strategy.

**Why this priority**: Attribution is essential for understanding why the strategy works or fails. Without it, optimization is guesswork.

**Independent Test**: Can be tested by running a backtest and verifying attribution report breaks down PnL by momentum_factor and breakout_factor contributions.

**Acceptance Scenarios**:

1. **Given** a completed backtest with multiple trades, **When** I request factor attribution, **Then** the system shows the percentage of total PnL attributable to momentum_factor vs breakout_factor.
2. **Given** a trade with recorded factor scores at entry, **When** I view the trade details, **Then** I can see which factor contributed more to the entry decision and its corresponding PnL contribution.

---

### Edge Cases

- What happens when price data is missing for a symbol on a given day? The system skips that symbol's calculation for that day and logs a warning.
- What happens when a factor score exactly equals the threshold? The system treats "equal to" as not crossing the threshold (no action).
- How does the system handle after-hours price gaps? The system uses the official daily close price; gaps between days are part of expected market behavior.
- What happens if the broker connection fails during live trading? The system pauses signal generation, logs the error, and alerts the user. No orders are submitted until connection is restored.
- What happens when there's insufficient historical data to calculate a feature (e.g., 20-day rolling calculation on day 10)? The system returns null for that feature and excludes the symbol from trading decisions until sufficient data exists.

## Requirements *(mandatory)*

### Functional Requirements

**Universe Management**
- **FR-001**: System MUST support a hardcoded universe of symbols (MU, GLD, GOOG) configurable via a simple configuration.
- **FR-002**: System MUST process all symbols in the universe identically using the same strategy logic.

**Feature Calculation**
- **FR-003**: System MUST calculate `roc_n` (Rate of Change) features for configurable lookback periods (default: 5 and 20 days). Formula: `(price[t] - price[t-n]) / price[t-n]`.
- **FR-004**: System MUST calculate `price_vs_ma_n` (Price vs Moving Average) features for configurable lookback periods (default: 20 days). Formula: `(price[t] - SMA[t,n]) / SMA[t,n]`.
- **FR-005**: System MUST calculate `price_vs_high_n` (Price vs N-day High) features for configurable lookback periods (default: 20 days). Formula: `(price[t] - max(high[t-n:t])) / max(high[t-n:t])`.
- **FR-006**: System MUST calculate `volume_zscore` as the z-score of current volume relative to recent history for configurable lookback periods (default: 20 days). Formula: `(volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])`.
- **FR-007**: System MUST calculate `volatility_n` using rolling standard deviation of returns for configurable lookback periods (default: 20 days). Formula: `std(returns[t-n:t])`.
- **FR-008**: All features MUST be calculated with proper lag to prevent lookahead bias (use only data available at calculation time).
- **FR-009**: All features MUST be computable on a daily basis from standard OHLCV data.

**Factor Composition**
- **FR-010**: System MUST compute `momentum_factor` as a function of roc_20 and price_vs_ma_20. Formula: `w1 * roc_20 + w2 * price_vs_ma_20` where weights are configurable.
- **FR-011**: System MUST compute `breakout_factor` as a function of price_vs_high_20 and volume_zscore. Formula: `w3 * price_vs_high_20 + w4 * volume_zscore` where weights are configurable.
- **FR-012**: System MUST support configurable weights for combining factors into a composite score. Formula: `composite = w_mom * momentum_factor + w_brk * breakout_factor`.

**Strategy Execution**
- **FR-013**: System MUST generate a buy signal when the composite factor score exceeds the entry threshold.
- **FR-014**: System MUST generate a sell signal when the composite factor score falls below the exit threshold.
- **FR-015**: System MUST support equal-weight position sizing across all positions.
- **FR-016**: System MUST support fixed risk per position as an alternative sizing method.
- **FR-017**: Entry and exit thresholds MUST be configurable parameters.

**Execution Modes**
- **FR-018**: System MUST support backtest mode using historical daily bars.
- **FR-019**: System MUST support paper trading mode using live market data with simulated execution.
- **FR-020**: System MUST support live trading mode with real order execution via broker adapter.
- **FR-021**: The core strategy logic (feature calculation, factor composition, signal generation) MUST be identical across all three execution modes.
- **FR-022**: Only the execution adapter (how orders are placed) MUST differ between modes.

**Performance & Attribution**
- **FR-023**: System MUST track and report PnL attribution by factor for all completed trades. Attribution = factor_weight × factor_score_at_entry × trade_pnl.
- **FR-024**: System MUST calculate standard performance metrics: total return, Sharpe ratio, max drawdown, win rate.
- **FR-025**: System MUST maintain a complete trade log with timestamps, prices, quantities, and factor scores at entry/exit.

### Key Entities

- **Universe**: Collection of tradeable symbols. Contains: symbol list, active status.
- **Feature**: A calculated indicator derived from price/volume data. Contains: name, lookback period, calculation method, value, timestamp.
- **Factor**: A composite signal derived from one or more features. Contains: name, component features, weights, current score.
- **Strategy**: The trading logic that converts factor scores to signals. Contains: entry threshold, exit threshold, position sizing method.
- **Position**: An open or closed holding. Contains: symbol, quantity, entry price, entry date, exit price, exit date, PnL.
- **Trade**: A record of a completed round-trip transaction. Contains: symbol, entry/exit details, factor scores at decision points, attributed PnL.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All three symbols (MU, GLD, GOOG) can complete a full backtest using the same codebase without any symbol-specific logic branches.
- **SC-002**: Given identical input data, backtest, paper, and live modes produce identical trading signals (100% signal agreement).
- **SC-003**: Factor PnL attribution sums to total portfolio PnL with less than 0.1% rounding error.
- **SC-004**: A backtest covering 1 year of daily data for 3 symbols completes within 30 seconds.
- **SC-005**: Paper trading mode processes incoming daily data and generates signals within 5 seconds of data receipt.
- **SC-006**: The system can transition from paper to live mode by changing only the execution adapter configuration, with no code changes to strategy logic.
- **SC-007**: All features demonstrate zero lookahead bias when validated against a future-only test set.

## Existing Infrastructure (Leverage These)

All infrastructure phases (1-3) are complete per STRATEGY.md. This feature creates a **minimal strategy** that utilizes the existing production-ready infrastructure.

The following components already exist in AQ_trading and should be reused:

**Strategy Framework** (`backend/src/strategies/`)
- Base Strategy ABC with `on_market_data()`, `on_fill()`, `on_start()`, `on_stop()` lifecycle
- Signal model (`Signal` dataclass) for intent-based trading
- Strategy Context providing read-only portfolio view
- Strategy Registry for discovery and configuration
- Strategy Engine for market data dispatch and signal forwarding

**Backtest Engine** (`backend/src/backtest/`)
- Event-driven simulation preventing lookahead bias (signals at bar[i], fills at bar[i+1])
- Warm-up period support for indicator initialization
- Metrics calculator (Sharpe, max drawdown, win rate)
- Benchmark comparison (buy-and-hold vs strategy)
- Trace builder for signal-to-fill audit trail

**Paper Trading** (`backend/src/broker/paper_broker.py`)
- PaperBroker with configurable slippage, partial fills, commissions
- Fill delay simulation
- Thread-safe fill callbacks

**Risk Manager** (`backend/src/risk/manager.py`)
- Position limits, portfolio limits, loss limits
- Kill switch with reason logging
- Dynamic risk bias from Redis
- Per-strategy pausing

**Order Pipeline** (`backend/src/orders/`)
- Signal → Order conversion
- Active order tracking
- Fill processing with idempotency
- Portfolio updates on fill

**Market Data** (`backend/src/market_data/`)
- Quote normalization and Redis caching
- CSV bar loading for backtesting
- Mock data source for testing

**What Needs to Be Built:**
- Feature calculation library (ROC, price_vs_ma, price_vs_high, volume z-score, volatility)
- Factor composition framework (momentum_factor, breakout_factor)
- PnL attribution by factor
- TrendBreakout strategy implementation using the existing Strategy base class

## Assumptions

- Historical daily OHLCV data is available for MU, GLD, and GOOG for at least the past 2 years (can be sourced via CSV or data provider).
- The existing Strategy base class and Signal model will be used as-is.
- The existing BacktestEngine will be used as-is for backtesting.
- The existing PaperBroker will be used for paper trading.
- Futu OpenAPI integration (stub exists) will be completed for live trading.
- Standard position sizing (equal weight or fixed risk) is sufficient for MVP; more sophisticated sizing is out of scope.
- Daily bar frequency is the only supported timeframe for MVP; intraday is out of scope.

## Out of Scope (MVP Exclusions)

- Hypothesis testing framework
- Constraint system for position limits or risk rules
- Regime detection state machine
- Pool/universe generator (dynamic symbol selection)
- Multi-timeframe analysis
- Options or derivatives trading
- Portfolio optimization beyond equal weight
- Machine learning-based factor generation
