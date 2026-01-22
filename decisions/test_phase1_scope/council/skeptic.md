# Skeptic Analysis

## Top Failure Modes

1. **Option A: Greeks calculation latency causes stale decision data** - Real-time Greeks require continuous recalculation as underlying price moves. If the calculation pipeline cannot keep pace with market data, traders see Greeks that are 30-60 seconds old, leading to incorrect position sizing or hedge decisions during volatile periods.

2. **Option A: Third-party Greeks data source becomes unreliable** - If relying on Futu's Greeks (assuming they provide them) or a calculation library, any API changes, rate limits, or calculation errors propagate directly to trading decisions. A silent failure in delta calculation could cause 2-3x position sizing errors.

3. **Option B: Trading options without Greeks leads to unhedged exposure** - Deferring Greeks means the trader has no systematic view of portfolio delta or theta decay. A position that appears small in notional terms may have outsized directional exposure, discovered only after a significant market move.

4. **Option A: Scope creep from "basic" to "complete"** - Once delta/theta display exists, the temptation to add gamma, vega, and portfolio-level Greeks becomes overwhelming. Each addition delays Phase 1 completion and introduces new failure surfaces.

5. **Option B: Manual Greeks tracking creates human error surface** - Trader calculates Greeks externally or mentally estimates them. Fatigue, distraction, or calculation errors create exposure that a systematic display would have caught.

## Catastrophic Risk

- **Trigger**: Sudden 3-sigma market move (flash crash, news event) while holding options positions without visible Greeks
- **Why it's overlooked**: Phase 1 timeline pressure prioritizes "getting something working" over risk visibility. Greeks feel like a "nice to have" because the trader "knows their positions."
- **Worst outcome**: Portfolio experiences 40-60% drawdown in a single session because actual delta exposure was 5x what the trader mentally estimated. Without Greeks display, there was no systematic check before the position grew to dangerous size.

## Early Warning Signals

- Signal 1: Trader opens external tools (broker terminal, spreadsheet) to check Greeks before making decisions - indicates the system is insufficient
- Signal 2: Position P&L moves in unexpected direction relative to underlying - reveals misunderstood exposure
- Signal 3: Time spent on manual Greeks calculations exceeds 15 minutes daily - system is creating operational overhead it should eliminate

## Recommendation

- If choosing Option A: **Require Greeks data staleness indicator** - display must show timestamp of last calculation and visually warn (red border, dimming) if data is >10 seconds old. Accept degraded display over wrong display. Additionally, cap scope explicitly: delta and theta only, no portfolio aggregation, no Greeks-based alerts.

- If choosing Option B: **Mandate pre-trade exposure checklist** - before any options trade executes, system must require manual confirmation of estimated delta exposure. Build the hook now so Greeks can automate this check in Phase 3. Also, implement hard position limits (max contracts, max notional) that don't require Greeks to enforce basic risk boundaries.
