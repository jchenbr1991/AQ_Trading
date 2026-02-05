# Tasks: Tiger Trading Broker Adapter

**Input**: Design documents from `/specs/004-tiger-broker-adapter/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: Install dependency and verify project structure

- [ ] T001 Add `tigeropen>=3.3.3,<4.0` to `backend/pyproject.toml` optional dependencies under `[project.optional-dependencies] tiger` and install
- [ ] T002 [P] Verify `config/brokers/` is gitignored and credential file has 0600 perms (FR-010)

---

## Phase 2: Foundational — LiveBroker Decorator Refactor (FR-007)

**Purpose**: Refactor LiveBroker to accept any `Broker` as inner broker. BLOCKS US1 config integration and US5.

**Why foundational**: The current LiveBroker is a stub with `broker_type: str`. FR-007 requires it to wrap any Broker implementation via decorator pattern. This must be done first so TigerBroker can be plugged in.

### Tests

- [ ] T003 Write failing tests for LiveBroker decorator pattern in `backend/tests/broker/test_live_broker.py`: constructor accepts `inner_broker: Broker`, delegates `submit_order`/`cancel_order`/`get_order_status`/`subscribe_fills` to inner broker after validation, existing risk validation still works
- [ ] T004 [P] Update existing LiveBroker tests in `backend/tests/broker/test_live_broker.py` to use new constructor signature (replace `broker_type="stub"` with mock inner broker)

### Implementation

- [ ] T005 Refactor `LiveBroker.__init__()` in `backend/src/broker/live_broker.py`: replace `broker_type: Literal["futu", "ibkr", "stub"]` with `inner_broker: Broker` parameter. Delegate `submit_order`, `cancel_order`, `get_order_status`, `subscribe_fills` to inner broker after risk validation passes. Keep all existing validation logic (RiskLimits, confirm_live_trading, validate_order). Remove stub order tracking (`_orders`, `_order_statuses` dicts) — inner broker handles that now
- [ ] T006 Verify all tests pass: `cd backend && python -m pytest tests/broker/test_live_broker.py -x -q`

**Checkpoint**: LiveBroker accepts any Broker implementation as inner broker. All existing tests pass with new signature.

---

## Phase 3: User Story 1 — Submit Orders via Tiger Trading (Priority: P1) 🎯 MVP

**Goal**: TigerBroker class implementing Broker protocol (submit_order, cancel_order, get_order_status, subscribe_fills)

**Independent Test**: Submit a limit order via mocked Tiger SDK, verify broker_order_id returned. Cancel it, verify status.

### Tests

- [ ] T007 Write failing tests for TigerBroker constructor in `backend/tests/broker/test_tiger_broker.py`: validates credentials_path exists with 0600 perms, account_id non-empty, env is PROD/SANDBOX. Raises ValueError otherwise
- [ ] T008 [P] Write failing tests for `TIGER_STATUS_MAP` constant and `_map_status()` helper in `backend/tests/broker/test_tiger_broker.py`: all 9 Tiger statuses map correctly per data-model.md, unmapped status defaults to PENDING with warning log
- [ ] T009 [P] Write failing tests for `submit_order` in `backend/tests/broker/test_tiger_broker.py`: mock TradeClient.place_order, verify limit order creates limit_order() + stock_contract(), market order creates market_order(), returns str(tiger_order_id), raises OrderSubmissionError on failure, raises OrderSubmissionError when disconnected
- [ ] T010 [P] Write failing tests for `cancel_order` in `backend/tests/broker/test_tiger_broker.py`: mock TradeClient.cancel_order, verify returns True, raises OrderCancelError on failure
- [ ] T011 [P] Write failing tests for `get_order_status` in `backend/tests/broker/test_tiger_broker.py`: mock TradeClient.get_order, verify returns mapped OrderStatus
- [ ] T012 [P] Write failing tests for `subscribe_fills` and fill pump in `backend/tests/broker/test_tiger_broker.py`: register callback, simulate PushClient transaction_changed via fill_queue, verify callback receives OrderFill with correct fill_id/price/quantity. Verify unknown fill (order not in _pending_orders) logs warning but does not crash. Covers SC-004 (zero lost fills during normal operation)
- [ ] T013 [P] Write failing tests for `connect`/`disconnect` in `backend/tests/broker/test_tiger_broker.py`: mock PushClient connect/subscribe, verify _connected flag, verify disconnect cleans up

### Implementation

- [ ] T014 Create `backend/src/broker/tiger_broker.py` with TigerBroker class skeleton: constructor with credential validation (path exists, 0600 perms, non-empty account_id, valid env), `TIGER_STATUS_MAP` dict constant, `_map_status()` helper
- [ ] T015 Implement `connect()` and `disconnect()` in `backend/src/broker/tiger_broker.py`: create TigerOpenClientConfig, TradeClient, PushClient, register callbacks (order_changed, transaction_changed, connect_callback, disconnect_callback), subscribe to order/transaction updates, start fill pump background task
- [ ] T016 Implement `submit_order()` in `backend/src/broker/tiger_broker.py`: check _connected, create stock_contract + market_order/limit_order, call asyncio.to_thread(trade_client.place_order), store tiger_order_id mapping, return str(id)
- [ ] T017 [P] Implement `cancel_order()` in `backend/src/broker/tiger_broker.py`: call asyncio.to_thread(trade_client.cancel_order)
- [ ] T018 [P] Implement `get_order_status()` in `backend/src/broker/tiger_broker.py`: call asyncio.to_thread(trade_client.get_order), map status via TIGER_STATUS_MAP
- [ ] T019 Implement `subscribe_fills()` and fill pump task in `backend/src/broker/tiger_broker.py`: store callback, _fill_pump reads from _fill_queue and calls callback. transaction_changed callback converts Tiger OrderTransactionData to OrderFill, enqueues via loop.call_soon_threadsafe. Unknown fills (not in _pending_orders) log warning
- [ ] T020 Implement reconnection logic in `backend/src/broker/tiger_broker.py`: disconnect_callback triggers reconnect with exponential backoff (1s, 2s, 4s, max 3 attempts), set _connected=False during reconnect
- [ ] T021 Implement rate-limit retry wrapper in `backend/src/broker/tiger_broker.py`: helper that wraps Tiger API calls, catches rate limit errors, retries with exponential backoff up to 3 times
- [ ] T022 Verify all tests pass for `backend/tests/broker/test_tiger_broker.py`. Include performance assertion: mocked `submit_order` round-trip completes within 5s (SC-003)

**Checkpoint**: TigerBroker implements full Broker protocol with mocked SDK. All edge cases covered.

---

## Phase 4: User Story 2 — Configure Broker via YAML (Priority: P1)

**Goal**: `broker.type: "tiger"` in YAML config creates TigerBroker via load_broker()

**Independent Test**: Load config with `broker.type: "tiger"`, verify TigerBroker instance created. Load with `broker.type: "paper"`, verify PaperBroker unchanged.

### Tests

- [ ] T023 Write failing tests for tiger config fields in `backend/tests/broker/test_config.py`: BrokerConfig.from_yaml parses `broker.tiger.credentials_path`, `account_id`, `env`, `max_reconnect_attempts` from YAML
- [ ] T024 [P] Write failing tests for `load_broker("tiger")` in `backend/tests/broker/test_config.py`: returns TigerBroker instance with correct params. Verify `load_broker("paper")` still returns PaperBroker (regression)
- [ ] T025 [P] Write failing test for invalid credentials path in `backend/tests/broker/test_config.py`: clear error message when path doesn't exist

### Implementation

- [ ] T026 Add tiger fields to `BrokerConfig` dataclass in `backend/src/broker/config.py`: `tiger_credentials_path: str = ""`, `tiger_account_id: str = ""`, `tiger_env: str = "PROD"`, `tiger_max_reconnect_attempts: int = 3`. Update `from_yaml()` to parse `broker.tiger.*` section
- [ ] T027 Add `"tiger"` case to `load_broker()` in `backend/src/broker/config.py`: import TigerBroker, create with config fields, return instance
- [ ] T028 Verify all tests pass: `cd backend && python -m pytest tests/broker/test_config.py -x -q`. Verify SC-001 (strategies execute via Tiger with config-only change) and SC-002 (switching broker.type is the only change needed)

**Checkpoint**: Config-driven broker creation works for tiger, paper (and futu stub) types. SC-001 and SC-002 validated.

---

## Phase 5: User Story 3 — Stream Real-Time Market Data from Tiger (Priority: P1)

**Goal**: TigerDataSource implementing DataSource protocol, configurable via `market_data.source: "tiger"`

**Independent Test**: Subscribe to AAPL via mocked PushClient, simulate quote_changed, verify MarketData event flows through queue.

### Tests

- [ ] T029 Write failing tests for TigerDataSource constructor in `backend/tests/market_data/test_tiger_source.py`: validates credentials_path, account_id, symbols non-empty, env valid. Raises ValueError otherwise
- [ ] T030 [P] Write failing tests for `start()`/`stop()` in `backend/tests/market_data/test_tiger_source.py`: mock PushClient connect/subscribe_quote, verify symbols subscribed, verify max_symbols limit logs warning for excess symbols
- [ ] T031 [P] Write failing tests for `quotes()` async iterator in `backend/tests/market_data/test_tiger_source.py`: simulate quote_changed callback, verify MarketData yielded with correct fields (price, bid, ask, volume, timestamp). Verify deduplication: stale timestamp discarded, newer timestamp accepted
- [ ] T032 [P] Write failing tests for `subscribe()` in `backend/tests/market_data/test_tiger_source.py`: idempotent, adds new symbols, respects max_symbols
- [ ] T033 [P] Write failing test for missing quote fields in `backend/tests/market_data/test_tiger_source.py`: quote with missing required field is skipped with warning log (no fabrication)

### Implementation

- [ ] T034 Create `backend/src/market_data/sources/tiger.py` with TigerDataSource class: constructor with credential validation, `_quote_queue`, `_last_timestamps`, `_max_symbols`
- [ ] T035 Implement `start()` and `stop()` in `backend/src/market_data/sources/tiger.py`: capture event loop, create TigerOpenClientConfig + PushClient, subscribe_quote with max_symbols enforcement, register callbacks
- [ ] T036 Implement `quote_changed` callback processing in `backend/src/market_data/sources/tiger.py`: extract fields from Tiger items, dedup by timestamp, skip if fields missing, create MarketData, enqueue via loop.call_soon_threadsafe
- [ ] T037 [P] Implement `subscribe()` in `backend/src/market_data/sources/tiger.py`: filter already-subscribed, check max_symbols, call push_client.subscribe_quote
- [ ] T038 Implement `quotes()` async iterator in `backend/src/market_data/sources/tiger.py`: async generator reading from _quote_queue
- [ ] T039 Implement reconnection in `backend/src/market_data/sources/tiger.py`: disconnect_callback with exponential backoff (1s, 2s, 4s), re-subscribe on success
- [ ] T040 Modify `MarketDataService.__init__()` in `backend/src/market_data/service.py`: accept optional `source: DataSource` parameter, default to `MockDataSource(config)` if not provided. Replace hardcoded `self._source = MockDataSource(config)` with `self._source = source or MockDataSource(config)`
- [ ] T041 Add market data source config wiring in `backend/src/market_data/models.py`: extend `MarketDataConfig` with `source: str = "mock"` field and `from_yaml()` to parse `market_data.source`. Add `load_data_source()` factory in `backend/src/market_data/config.py` (new file) that creates TigerDataSource (reusing same credentials_path from broker config per FR-012) or MockDataSource based on config. Wire into MarketDataService instantiation. Verify SC-008 (switching source requires only config change)
- [ ] T042 Verify all tests pass for `backend/tests/market_data/test_tiger_source.py` and existing `backend/tests/market_data/` tests (regression). Include performance assertion: mocked quote callback to `quotes()` yield completes within 2s (SC-007)

**Checkpoint**: TigerDataSource streams quotes via mocked SDK. MarketDataService accepts any DataSource.

---

## Phase 6: User Story 4 — Query Positions and Account from Tiger (Priority: P2)

**Goal**: TigerBroker implements BrokerQuery protocol (get_positions, get_account)

**Independent Test**: Call get_positions/get_account against mocked TradeClient, verify correct BrokerPosition/BrokerAccount mapping.

### Tests

- [ ] T043 Write failing tests for `get_positions()` in `backend/tests/broker/test_tiger_broker.py`: mock TradeClient.get_positions, verify BrokerPosition mapping (symbol, quantity, avg_cost, market_value, asset_type=STOCK)
- [ ] T044 [P] Write failing tests for `get_account()` in `backend/tests/broker/test_tiger_broker.py`: mock TradeClient.get_assets, verify BrokerAccount mapping (cash, buying_power, total_equity, margin_used)

### Implementation

- [ ] T045 Implement `get_positions()` in `backend/src/broker/tiger_broker.py`: call asyncio.to_thread(trade_client.get_positions), map Tiger positions to list[BrokerPosition]
- [ ] T046 [P] Implement `get_account()` in `backend/src/broker/tiger_broker.py`: call asyncio.to_thread(trade_client.get_assets), map Tiger assets to BrokerAccount
- [ ] T047 Verify tests pass: `cd backend && python -m pytest tests/broker/test_tiger_broker.py -x -q -k "get_positions or get_account"`

**Checkpoint**: TigerBroker implements full BrokerQuery protocol. Positions and account data mapped correctly.

---

## Phase 7: User Story 5 — LiveBroker Wraps Tiger with Risk Controls (Priority: P2)

**Goal**: LiveBroker wrapping TigerBroker applies all risk validation before delegating to Tiger

**Independent Test**: Configure LiveBroker with TigerBroker inner broker and max_position_size=1000, submit order for 2000 shares — rejected before reaching Tiger.

### Tests

- [ ] T048 Write failing integration tests in `backend/tests/broker/test_live_broker.py`: LiveBroker wrapping mock TigerBroker — verify risk validation rejects oversized orders, daily loss limits, confirmation required. Verify valid orders are delegated to inner broker

### Implementation

- [ ] T049 Verify integration in `backend/tests/broker/test_live_broker.py`: LiveBroker(inner_broker=TigerBroker(...)) delegates correctly after validation. This should work without code changes if Phase 2 (T005) was implemented correctly — verification only. Verify SC-005 (risk controls apply identically across brokers)
- [ ] T050 Verify all tests pass: `cd backend && python -m pytest tests/broker/ -x -q`

**Checkpoint**: Risk controls apply identically regardless of inner broker (Paper or Tiger).

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, credential security verification

- [ ] T051 Run full test suite: `cd backend && python -m pytest tests/ -x -q -m 'not timescaledb'`. All phases must pass before this task
- [ ] T052 [P] Verify credential security (FR-010) in `config/brokers/` and `.gitignore`: no credentials in git history (`git log -p | grep -i private_key`), no credential content in log output, config/brokers/ gitignored, pre-commit detects secrets (SC-006)
- [ ] T053 [P] Verify `specs/004-tiger-broker-adapter/quickstart.md` accuracy: all commands work, all paths correct
- [ ] T054 Update Broker protocol docstring in `backend/src/broker/base.py` to include TigerBroker in implementations list
- [ ] T055 [P] Update DataSource protocol docstring in `backend/src/market_data/sources/base.py` to include TigerDataSource in implementations list

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (LiveBroker Refactor)**: Depends on Phase 1. **BLOCKS** Phase 4 (config needs new LiveBroker), Phase 7 (wrapping)
- **Phase 3 (US1 - Orders)**: Depends on Phase 1. Can start in parallel with Phase 2
- **Phase 4 (US2 - Config)**: Depends on Phase 2 + Phase 3 (needs both refactored LiveBroker and TigerBroker class)
- **Phase 5 (US3 - Market Data)**: Depends on Phase 1 only. **Independent** of Phases 2-4
- **Phase 6 (US4 - Positions)**: Depends on Phase 3 (extends TigerBroker)
- **Phase 7 (US5 - Risk Controls)**: Depends on Phase 2 + Phase 3 (LiveBroker wrapping TigerBroker)
- **Phase 8 (Polish)**: Depends on all prior phases

### Parallel Opportunities

After Phase 1:
- Phase 2 (LiveBroker refactor) and Phase 3 (TigerBroker) can run in parallel
- Phase 5 (TigerDataSource) can start as soon as Phase 1 completes — fully independent

After Phase 3:
- Phase 4 (Config) and Phase 6 (Positions) can run in parallel
- Phase 7 (Risk Controls) can start once Phase 2 + Phase 3 are done

### Within Each Phase

- Tests MUST be written first and FAIL before implementation
- Models/constants before methods
- Core methods before edge-case handling
- Verify tests pass at each checkpoint

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Phase 1: Setup
2. Phase 2: LiveBroker refactor (unblocks config integration)
3. Phase 3: TigerBroker (core order execution)
4. Phase 4: Config (makes it usable)
5. **STOP and VALIDATE**: Submit a mocked order via config

### Full Delivery

6. Phase 5: Market data (can be parallel with 2-4)
7. Phase 6: Positions/account
8. Phase 7: Risk controls integration
9. Phase 8: Polish

---

## Notes

- All Tiger SDK calls are mocked in tests — no live credentials needed
- `asyncio.to_thread()` wraps all synchronous TradeClient calls
- `loop.call_soon_threadsafe()` bridges PushClient callbacks to asyncio
- [P] tasks within a phase can run in parallel (different files)
- Commit after each phase checkpoint
