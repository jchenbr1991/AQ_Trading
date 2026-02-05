# Feature Specification: Tiger Trading Broker Adapter

**Feature Branch**: `004-tiger-broker-adapter`
**Created**: 2026-02-05
**Status**: Draft
**Input**: User description: "准备tiger trading的broker适配，系统在Tiger上跑起来，后续可通过配置切换futu和tiger"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit Orders via Tiger Trading (Priority: P1)

As a trader, I want the system to submit, cancel, and track orders through Tiger Trading's API so that I can execute my algorithmic strategies on a live broker.

**Why this priority**: This is the core value — without order execution, nothing else matters. The existing `Broker` Protocol defines exactly 4 methods (submit_order, cancel_order, get_order_status, subscribe_fills) that must work for any strategy to run.

**Independent Test**: Can be tested by submitting a limit order through the Tiger API, verifying it appears in Tiger's system, cancelling it, and confirming the cancellation. Delivers the ability to run any existing strategy on Tiger.

**Acceptance Scenarios**:

1. **Given** a valid Tiger API connection, **When** a limit buy order for 100 shares of AAPL is submitted, **Then** the system returns a broker_order_id and the order appears in Tiger's order book
2. **Given** an open order on Tiger, **When** cancel_order is called with its broker_order_id, **Then** the order is cancelled and get_order_status returns CANCELLED
3. **Given** an order is filled on Tiger, **When** a fill occurs, **Then** the registered fill callback is invoked with correct fill details (price, quantity, fill_id, timestamp)
4. **Given** a partial fill on Tiger, **When** 50 of 100 shares are filled, **Then** the fill callback fires with quantity=50 and get_order_status returns PARTIAL_FILL

---

### User Story 2 - Configure Broker via YAML (Priority: P1)

As a system operator, I want to select Tiger or Paper broker through a YAML configuration file so that I can switch brokers without code changes.

**Why this priority**: Equal to P1 because the existing system already uses config-driven broker selection. Tiger must integrate into this pattern to be usable. This also enables the Futu/Tiger switching goal.

**Independent Test**: Can be tested by changing `broker.type: "tiger"` in a strategy YAML config, starting the strategy, and verifying it connects to Tiger. Switch back to `broker.type: "paper"` and verify paper trading resumes.

**Acceptance Scenarios**:

1. **Given** a strategy config with `broker.type: "tiger"` and valid Tiger credentials path, **When** the strategy starts, **Then** a Tiger broker connection is established
2. **Given** a strategy config with `broker.type: "paper"`, **When** the strategy starts, **Then** the PaperBroker is used (existing behavior unchanged)
3. **Given** an invalid Tiger credentials path in config, **When** the strategy starts, **Then** a clear error message is shown and the strategy does not start

---

### User Story 3 - Stream Real-Time Market Data from Tiger (Priority: P1)

As a trader, I want the system to receive real-time quote data from Tiger Trading so that my strategies can generate signals based on live market prices instead of mock data.

**Why this priority**: Without real-time market data, strategies cannot generate meaningful signals. This is a prerequisite for any live trading — the system needs prices to make trading decisions. The existing `DataSource` protocol and `MarketDataService` already define the integration point.

**Independent Test**: Can be tested by subscribing to AAPL quotes via Tiger, verifying that `MarketData` events (price, bid, ask, volume, timestamp) flow through the `MarketDataService` to a test consumer. Delivers the ability to run strategies on real market data.

**Acceptance Scenarios**:

1. **Given** a valid Tiger API connection and a strategy subscribed to AAPL, **When** Tiger sends a quote update, **Then** a `MarketData` event with correct price, bid, ask, volume, and timestamp is delivered to the strategy via `MarketDataService`
2. **Given** a strategy config with `market_data.source: "tiger"`, **When** the strategy starts, **Then** the system connects to Tiger's quote feed and begins streaming data for configured symbols
3. **Given** a strategy config with `market_data.source: "mock"`, **When** the strategy starts, **Then** the existing mock data source is used (existing behavior unchanged)
4. **Given** a Tiger quote feed connection drop, **When** the connection is lost, **Then** the system logs a warning and attempts to reconnect; stale quotes are detected via the existing `QuoteSnapshot` staleness mechanism

---

### User Story 4 - Query Positions and Account from Tiger (Priority: P2)

As a trader, I want the system to fetch my current positions and account balance from Tiger so that the reconciliation service can verify local state against broker state.

**Why this priority**: Important for production safety but the system can initially run without reconciliation. The existing `BrokerQuery` protocol (get_positions, get_account) needs Tiger implementation for the reconciliation service to work.

**Independent Test**: Can be tested by calling get_positions and get_account against a Tiger account with known holdings, and verifying the returned data matches what Tiger's web interface shows.

**Acceptance Scenarios**:

1. **Given** a connected Tiger account with existing positions, **When** get_positions is called, **Then** all positions are returned with correct symbol, quantity, average cost, market value, and asset type (matching the BrokerPosition dataclass)
2. **Given** a connected Tiger account, **When** get_account is called, **Then** account cash, buying power, total equity, and margin used are returned accurately (matching the BrokerAccount dataclass)

---

### User Story 5 - LiveBroker Wraps Tiger with Risk Controls (Priority: P2)

As a risk manager, I want the existing LiveBroker pre-trade validation (position limits, order value limits, daily loss limits) to apply to Tiger orders so that risk controls are enforced regardless of which broker is used.

**Why this priority**: Critical for production safety but can be layered on after basic Tiger execution works. The existing LiveBroker already has validation logic — it needs to delegate to TigerBroker instead of raising NotImplementedError.

**Independent Test**: Can be tested by configuring LiveBroker with a TigerBroker as inner broker and risk limits, then submitting an order that exceeds position size limit — it should be rejected before reaching Tiger.

**Acceptance Scenarios**:

1. **Given** LiveBroker wrapping TigerBroker with max_position_size=1000, **When** an order for 2000 shares is submitted, **Then** the order is rejected with a risk limit error before reaching Tiger
2. **Given** LiveBroker wrapping TigerBroker with max_daily_loss=$5000, **When** daily losses exceed $5000, **Then** subsequent orders are rejected
3. **Given** LiveBroker with require_confirmation=true, **When** an order is submitted without calling confirm_live_trading(), **Then** the order is rejected

---

### Edge Cases

- What happens when Tiger API connection drops mid-session? System must detect disconnection and prevent new orders from being submitted, with clear error reporting.
- What happens when a fill notification is received for an order the system doesn't recognize? The fill callback should log a warning and not crash.
- What happens when Tiger returns a rate limit error? The system should retry with backoff up to 3 times before raising an error.
- What happens when Tiger's order status mapping doesn't align with our OrderStatus enum? Each Tiger status must be explicitly mapped; unmapped statuses should be logged and treated as PENDING.
- What happens when credentials file is missing or malformed? A clear error at startup, not a cryptic runtime failure.
- What happens when Tiger imposes subscription limits on the number of symbols for real-time quotes? The system should respect API limits, log a warning if the requested symbol count exceeds the allowed maximum, and subscribe to as many as permitted.
- What happens when the Tiger quote feed sends duplicate or out-of-order quotes? The system should deduplicate by timestamp and discard stale quotes that arrive after newer ones.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement a TigerBroker class that conforms to the existing `Broker` Protocol (submit_order, cancel_order, get_order_status, subscribe_fills)
- **FR-002**: System MUST implement the `BrokerQuery` Protocol for Tiger (get_positions, get_account)
- **FR-003**: System MUST load Tiger API credentials from an external config file (not hardcoded), with the credentials path specified in the strategy YAML config
- **FR-004**: System MUST map Tiger order statuses to the existing OrderStatus enum (PENDING, SUBMITTED, PARTIAL_FILL, FILLED, CANCELLED, REJECTED, EXPIRED)
- **FR-005**: System MUST support Tiger's fill notification mechanism and deliver fills to the registered callback with unique fill_ids
- **FR-006**: The broker config loader (load_broker) MUST support `broker.type: "tiger"` in YAML config (consistent with existing `broker.type` key convention) and create a TigerBroker instance
- **FR-007**: The LiveBroker MUST be refactored to accept any Broker Protocol implementation as an inner broker (decorator pattern) rather than containing broker-specific logic directly. This requires changing the current constructor from `broker_type: Literal["futu", "ibkr", "stub"]` to accept an `inner_broker: Broker` parameter
- **FR-008**: System MUST handle Tiger API connection lifecycle (connect, disconnect, reconnect on failure)
- **FR-009**: System MUST ensure thread safety for fill callbacks from Tiger's SDK
- **FR-010**: Credentials (private keys, account IDs) MUST NOT be committed to version control; credentials files MUST be listed in .gitignore. Credentials files on disk MUST have restricted file permissions (owner-read-only, 0600). The system MUST NOT log or expose credential content in error messages or stack traces
- **FR-011**: System MUST implement a TigerDataSource class that conforms to the existing `DataSource` protocol, producing `MarketData` events (symbol, price, bid, ask, volume, timestamp) from Tiger's real-time quote feed. The TigerDataSource receives its symbol list from the strategy configuration (same symbols the strategy trades) and subscribes to Tiger's quote feed for those symbols at startup
- **FR-012**: The market data source MUST be configurable via strategy YAML config (`market_data.source: "tiger" | "mock"`), with the TigerDataSource sharing the same Tiger credentials as TigerBroker
- **FR-013**: The TigerDataSource MUST handle quote feed disconnections gracefully, with automatic reconnection and stale quote detection via the existing `QuoteSnapshot` mechanism

### Key Entities

- **TigerBroker**: The adapter that translates between AQ Trading's Broker Protocol and Tiger Trading's API. Holds connection state and credential references.
- **TigerDataSource**: The adapter that translates Tiger's real-time quote feed into the existing `DataSource` protocol, producing `MarketData` events for the `MarketDataService`.
- **BrokerConfig**: Extended configuration dataclass that includes Tiger-specific settings (credentials path, environment, account ID) alongside existing paper and futu settings.
- **Order Mapping**: Translation layer between AQ Trading's Order model and Tiger's order format, including order type mapping (market, limit) and status mapping.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing strategies can execute orders through Tiger Trading without code changes to the strategy itself — only configuration changes needed
- **SC-002**: Switching between Paper and Tiger broker requires changing only the `broker.type` field in the strategy YAML config
- **SC-003**: Order submission through Tiger completes within 5 seconds under normal network conditions
- **SC-004**: All order lifecycle events (submit, fill, partial fill, cancel) are correctly received and processed with zero lost fills during normal operation
- **SC-005**: Risk controls (position limits, order value limits, daily loss limits) apply identically whether using Paper, Tiger, or any future broker
- **SC-006**: Zero credentials appear in version control history, application logs, or error output. Credentials files have 0600 permissions. Pre-commit hooks detect and block any credential commits
- **SC-007**: Strategies receive real-time market data from Tiger with quote latency under 2 seconds from Tiger's feed to strategy signal generation under normal network conditions
- **SC-008**: Switching market data source between mock and Tiger requires changing only the `market_data.source` field in the strategy YAML config

## Assumptions

- Tiger Trading's Python SDK (`tigeropen`) is available and supports the required order types (market, limit)
- The existing `tiger_openapi_config.properties` file format is the standard Tiger credential format
- Tiger's API supports async or can be wrapped in async (thread pool executor)
- The system only needs to support stock orders initially (not options or futures through Tiger)
- Tiger's fill notification mechanism provides unique fill identifiers or sufficient data to generate them
- Tiger's API permissions grant both trading and real-time market data access under the same credentials and account entitlement. If separate entitlements are required, this will be discovered during implementation and the credential configuration will be extended accordingly
