# Slice 3.2: Audit Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Complete compliance audit trail for orders, config changes, alerts, and system events with tamper detection and 90-day retention.

**Architecture:** AuditService receives events from business modules, computes diff/checksum with chain integrity, persists to TimescaleDB hypertable with Tier-0 sync / Tier-1 async write paths.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, TimescaleDB, jsonpatch

---

## Task 1: Audit Models and Enums

**Files:**
- Create: `backend/src/audit/__init__.py`
- Create: `backend/src/audit/models.py`
- Create: `backend/tests/audit/__init__.py`
- Create: `backend/tests/audit/test_models.py`

**Requirements:**

1. `AuditEventType` enum with event types:
   - Orders: `ORDER_PLACED`, `ORDER_ACKNOWLEDGED`, `ORDER_FILLED`, `ORDER_CANCELLED`, `ORDER_REJECTED`
   - Config: `CONFIG_CREATED`, `CONFIG_UPDATED`, `CONFIG_DELETED`
   - Alerts: `ALERT_EMITTED`, `ALERT_ACKNOWLEDGED`, `ALERT_RESOLVED`
   - System: `SYSTEM_STARTED`, `SYSTEM_STOPPED`, `HEALTH_CHANGED`
   - Security: `AUTH_LOGIN`, `AUTH_LOGOUT`, `AUTH_FAILED`, `PERMISSION_CHANGED`

2. `ActorType` enum: `USER`, `SYSTEM`, `API`, `SCHEDULER`

3. `AuditSeverity` enum: `INFO`, `WARNING`, `CRITICAL`

4. `ResourceType` enum: `ORDER`, `POSITION`, `CONFIG`, `ALERT`, `STRATEGY`, `ACCOUNT`, `PERMISSION`, `SESSION`

5. `EventSource` enum: `WEB`, `API`, `WORKER`, `SCHEDULER`, `SYSTEM`, `CLI`

6. `ValueMode` enum: `DIFF`, `SNAPSHOT`, `REFERENCE`

7. `AuditEvent` frozen dataclass with all fields from design

**TDD:** Write tests first, then implement.

**Commit:** `feat(audit): add audit models and enums`

---

## Task 2: Tier Configuration and Value Mode Rules

**Files:**
- Create: `backend/src/audit/config.py`
- Create: `backend/tests/audit/test_config.py`

**Requirements:**

1. `TIER_0_EVENTS` frozenset - sync write events (orders, config, permissions, auth)

2. `TIER_1_EVENTS` frozenset - async write events (alerts, health, system)

3. `VALUE_MODE_CONFIG` dict mapping event_type -> ValueMode

4. `CHECKSUM_FIELDS` list - fields included in checksum

5. `REDACTION_RULES` dict - sensitive field patterns by resource_type

6. Constants: `MAX_VALUE_SIZE_BYTES = 32768`, `MAX_METADATA_SIZE_BYTES = 8192`

7. Helper functions:
   - `get_tier(event_type: AuditEventType) -> int` (0 or 1)
   - `get_value_mode(event_type: AuditEventType) -> ValueMode`
   - `is_sync_required(event_type: AuditEventType) -> bool`

**Commit:** `feat(audit): add tier configuration and value mode rules`

---

## Task 3: Checksum and Chain Integrity

**Files:**
- Create: `backend/src/audit/integrity.py`
- Create: `backend/tests/audit/test_integrity.py`

**Requirements:**

1. `compute_checksum(event: AuditEvent, sequence_id: int, prev_checksum: str | None) -> str`:
   - Use CHECKSUM_FIELDS for canonical form
   - SHA256 hash
   - Include prev_checksum for chain

2. `verify_checksum(event_row: dict) -> bool`:
   - Recompute and compare

3. `verify_chain(events: list[dict]) -> tuple[bool, list[str]]`:
   - Verify sequence is monotonic
   - Verify each prev_checksum matches previous checksum
   - Return (valid, list of errors)

**Commit:** `feat(audit): add checksum and chain integrity verification`

---

## Task 4: Diff and Redaction Utilities

**Files:**
- Create: `backend/src/audit/diff.py`
- Create: `backend/tests/audit/test_diff.py`

**Requirements:**

1. `compute_diff_jsonpatch(old: dict | None, new: dict | None) -> dict | None`:
   - Use jsonpatch library
   - Return JSON Patch format (RFC 6902)
   - Return None if no changes

2. `redact_sensitive_fields(data: dict | None, resource_type: str) -> dict | None`:
   - Apply REDACTION_RULES
   - Mask sensitive values (keep first 2 and last 2 chars)

3. `enforce_size_limit(value: dict | None, resource_type: str, resource_id: str) -> tuple[dict | None, str | None, ValueMode]`:
   - Check against MAX_VALUE_SIZE_BYTES
   - Return (value, hash, mode)
   - Auto-switch to REFERENCE if too large

**Dependency:** Add `jsonpatch` to pyproject.toml

**Commit:** `feat(audit): add diff computation and redaction utilities`

---

## Task 5: Database Migration

**Files:**
- Create: `backend/alembic/versions/005_audit_logs.py`

**Requirements:**

1. Create `audit_sequence` PostgreSQL sequence

2. Create `audit_chain_head` table:
   - chain_key VARCHAR(100) PRIMARY KEY
   - checksum VARCHAR(64) NOT NULL
   - sequence_id BIGINT NOT NULL
   - updated_at TIMESTAMPTZ NOT NULL

3. Create `audit_logs` table with all columns from design:
   - TimescaleDB hypertable (1 day chunks)
   - Compression policy (7 days)
   - All CHECK constraints
   - Size limits on JSONB fields

4. Create indexes:
   - idx_audit_resource (resource_type, resource_id, timestamp DESC)
   - idx_audit_actor (actor_type, actor_id, timestamp DESC)
   - idx_audit_event_type (event_type, timestamp DESC)
   - idx_audit_request (request_id)
   - idx_audit_correlation (correlation_id) WHERE NOT NULL
   - idx_audit_sequence (sequence_id DESC)

5. Role permissions:
   - REVOKE UPDATE, DELETE on audit_logs
   - GRANT INSERT, SELECT on audit_logs
   - GRANT usage on sequence

**Commit:** `feat(audit): add database migration for audit logs`

---

## Task 6: Audit Repository

**Files:**
- Create: `backend/src/audit/repository.py`
- Create: `backend/tests/audit/test_repository.py`

**Requirements:**

1. `AuditRepository` class with AsyncSession

2. `persist_audit_event(event: AuditEvent) -> tuple[int, str]`:
   - Lock chain_head FOR UPDATE
   - Get prev_checksum
   - Get nextval from sequence
   - Compute checksum
   - INSERT audit_logs
   - UPDATE audit_chain_head
   - Return (sequence_id, checksum)

3. `get_audit_event(event_id: UUID) -> dict | None`

4. `query_audit_logs(filters: AuditQueryFilters) -> list[dict]`:
   - Support filters: event_type, resource_type, resource_id, actor_id, time_range
   - Pagination with offset/limit

5. `get_chain_head(chain_key: str) -> dict | None`

6. `verify_chain_integrity(chain_key: str, limit: int = 100) -> tuple[bool, list[str]]`

**Commit:** `feat(audit): add audit repository with chain integrity`

---

## Task 7: Audit Service

**Files:**
- Create: `backend/src/audit/service.py`
- Create: `backend/tests/audit/test_service.py`

**Requirements:**

1. `AuditService` class:
   - __init__(repository, async_queue)
   - Tier-0 queue (sync)
   - Tier-1 queue (async with asyncio.Queue)

2. `log(event_type, actor_id, actor_type, resource_type, resource_id, ...) -> UUID`:
   - Create AuditEvent
   - Apply redaction
   - Compute diff (if old/new provided)
   - Enforce size limits
   - Route to Tier-0 or Tier-1

3. `_persist_sync(event: AuditEvent)` - Tier-0 direct write

4. `_enqueue_async(event: AuditEvent)` - Tier-1 queue

5. `start_workers(num_workers: int = 2)` - Start async workers

6. `stop()` - Graceful shutdown

**Commit:** `feat(audit): add AuditService with tiered write paths`

---

## Task 8: Audit Factory

**Files:**
- Create: `backend/src/audit/factory.py`
- Create: `backend/tests/audit/test_factory.py`

**Requirements:**

1. `create_audit_event(...)` factory function:
   - Generate UUID
   - Set timestamp to UTC now
   - Validate required fields
   - Apply value_mode based on event_type

2. `AuditContext` context manager for request-scoped auditing:
   ```python
   async with AuditContext(request_id, actor_id, actor_type, source) as ctx:
       ctx.log(AuditEventType.ORDER_PLACED, ...)
   ```

3. Helper functions for common audit patterns:
   - `audit_order_event(order, event_type, old_status, new_status)`
   - `audit_config_change(config_key, old_value, new_value)`

**Commit:** `feat(audit): add audit factory and context manager`

---

## Task 9: Audit API Endpoints

**Files:**
- Create: `backend/src/api/audit.py`
- Create: `backend/tests/api/test_audit.py`

**Requirements:**

1. Pydantic models:
   - `AuditLogResponse`
   - `AuditLogListResponse`
   - `AuditQueryParams`
   - `ChainIntegrityResponse`

2. Endpoints:
   - `GET /api/audit` - List audit logs with filters
   - `GET /api/audit/{event_id}` - Get single audit event
   - `GET /api/audit/stats` - Audit statistics (counts by type, actor, resource)
   - `GET /api/audit/integrity/{chain_key}` - Verify chain integrity

3. Register router in main.py

**Commit:** `feat(audit): add audit API endpoints`

---

## Task 10: Frontend Types and Hook

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/hooks/useAudit.ts`
- Modify: `frontend/src/hooks/index.ts`

**Requirements:**

1. TypeScript types:
   - `AuditEventType`, `ActorType`, `AuditSeverity`
   - `AuditLog` interface
   - `AuditLogListResponse`
   - `AuditStats`
   - `ChainIntegrity`

2. Hooks:
   - `useAuditLogs(filters)` - Query with filters
   - `useAuditStats()` - Statistics
   - `useChainIntegrity(chainKey)` - Integrity check

**Commit:** `feat(frontend): add audit types and hooks`

---

## Task 11: Audit Dashboard Page

**Files:**
- Create: `frontend/src/components/AuditStats.tsx`
- Create: `frontend/src/components/AuditTable.tsx`
- Create: `frontend/src/components/AuditFilters.tsx`
- Create: `frontend/src/pages/AuditPage.tsx`
- Modify: `frontend/src/App.tsx`

**Requirements:**

1. `AuditStats` - Cards showing counts by severity, event type

2. `AuditFilters` - Filter controls for event_type, resource_type, actor, date range

3. `AuditTable` - Table with columns:
   - Timestamp, Event Type, Actor, Resource, Severity
   - Expandable row for details (old/new values)

4. `AuditPage` - Combine components

5. Add route `/audit` in App.tsx

**Commit:** `feat(frontend): add AuditPage with stats and filters`

---

## Task 12: Setup and Integration

**Files:**
- Create: `backend/src/audit/setup.py`
- Modify: `backend/src/main.py`

**Requirements:**

1. `init_audit_service(db_session) -> AuditService`:
   - Create repository
   - Create service with workers
   - Store global instance

2. `get_audit_service() -> AuditService | None`

3. Update main.py lifespan to mention audit service

4. Example integration helpers for other modules

**Commit:** `feat(audit): add setup module and integration`

---

## Task 13: Final Exports and Tests

**Files:**
- Update: `backend/src/audit/__init__.py`

**Requirements:**

1. Export all public classes and functions

2. Run full test suite: `pytest tests/audit/ -v`

3. Verify all tests pass

**Commit:** `feat(audit): complete Slice 3.2 Audit Logging - final exports`

---

## Summary

| Task | Description | Key Files |
|------|-------------|-----------|
| 1 | Audit Models | audit/models.py |
| 2 | Tier Config | audit/config.py |
| 3 | Checksum/Chain | audit/integrity.py |
| 4 | Diff/Redaction | audit/diff.py |
| 5 | DB Migration | alembic/005_audit_logs.py |
| 6 | Repository | audit/repository.py |
| 7 | Service | audit/service.py |
| 8 | Factory | audit/factory.py |
| 9 | API | api/audit.py |
| 10 | Frontend Types | types/index.ts, hooks/useAudit.ts |
| 11 | Dashboard | pages/AuditPage.tsx |
| 12 | Setup | audit/setup.py |
| 13 | Final | audit/__init__.py |

**Exit Criteria:**
- Audit logs persist with chain integrity
- Tier-0 events sync, Tier-1 events async
- Sensitive fields redacted
- 32KB size limit enforced
- Dashboard shows audit history with filters
- Chain integrity verifiable via API
