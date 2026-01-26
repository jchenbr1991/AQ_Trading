# Slice 3.3: Graceful Degradation Design

> **Architecture**: Central Policy + Local Execution
> **Principle**: 没有任何一个组件，拥有把 Trading Hot Path 拉下水的权力。

## 1. Scope

### In Scope (Hot Path - 显式降级设计)

| 组件 | 策略 | 场景 | 动作 |
|------|------|------|------|
| Broker & Market Data | Circuit Breaker (硬) | 网络中断, API失败, Rate limit | 停止开仓, 撤销未成交, 进入 Safe Mode |
| Order/Risk Engine | Fail-Safe (默认拒绝) | 风控超时, 计算不可用 | 视为风控不通过, 拒绝下单 |
| Database | Buffering + Read-Only | DB连接闪断, 写入失败 | 暂存 Memory/WAL, 尝试重连 |
| Alerts | Silent Fail + 本地队列 | 发送失败, 通道抖动 | 写本地日志, 异步重试, 不阻塞交易 |

### Out of Scope (Cold Path - 隔离 + 软失败)

| 组件 | 定位 | 策略 |
|------|------|------|
| Backtesting | 研发工具/CLI | Crash即可, 重跑 |
| Reconciliation | 盘后批处理 | 失败即告警, 人工介入 |
| Audit Logging | 合规归档 | 写失败→本地缓冲, 不阻塞交易 |

---

## 2. Core Architecture

### 2.1 SystemStateService (中心)

单一真相源 (Single Source of Truth):
- 维护 `SystemMode` + `SystemLevel` 状态机
- 处理事件归一化 + 状态流转 + 广播
- 记录 mode change → audit event + alert (异步)
- **Single Writer**: 只有 SystemStateService 可修改状态

```python
class SystemMode(Enum):
    NORMAL = "normal"           # 全功能
    DEGRADED = "degraded"       # 受限运行
    SAFE_MODE = "safe_mode"     # 保护资金 (控制面可用)
    SAFE_MODE_DISCONNECTED = "safe_mode_disconnected"  # 保护资金 (控制面不可用)
    HALT = "halt"               # 需人工介入
    RECOVERING = "recovering"   # 恢复编排中

# 严格优先级 (数字越大越严重)
MODE_PRIORITY = {
    SystemMode.NORMAL: 0,
    SystemMode.RECOVERING: 1,
    SystemMode.DEGRADED: 2,
    SystemMode.SAFE_MODE: 3,
    SystemMode.SAFE_MODE_DISCONNECTED: 4,
    SystemMode.HALT: 5,
}

class SystemLevel(Enum):
    """Internal health level for hysteresis tracking."""
    HEALTHY = "healthy"         # 正常
    UNSTABLE = "unstable"       # 抖动中, 尚未触发降级
    TRIPPED = "tripped"         # 已触发降级
```

### 2.2 SystemLevel 与 SystemMode 的关系

**明确映射规则:**

| SystemLevel | SystemMode 行为 | Alert 策略 |
|-------------|----------------|------------|
| HEALTHY | 保持当前 mode (可能是 NORMAL 或 RECOVERING) | 无 |
| UNSTABLE | **不改变 mode**, 但提高采样频率 | WARNING 级 alert (可配置) |
| TRIPPED | 触发 Decision Matrix, 锁定 min_dwell_time | CRITICAL alert |

```python
# UNSTABLE 是预警状态, 不触发 mode 变更
if new_level == SystemLevel.UNSTABLE:
    self._increase_probe_frequency()
    if config.alert_on_unstable:
        await self._emit_warning_alert(source, reason)
    # mode 保持不变

# TRIPPED 触发实际降级
if new_level == SystemLevel.TRIPPED:
    target_mode = self._decision_matrix.get_target_mode(reason_code)
    await self._transition_to(target_mode, min_dwell=config.min_safe_mode_seconds)
```

### 2.3 Cold Start (启动即保护)

**系统启动时默认状态: `RECOVERING`**

逻辑: 程序刚启动时内存是空的, 不知道市场数据是否新鲜。
必须强制跑一遍 Recovery Orchestration, 全绿之后才自动切入 NORMAL。

```python
def on_startup():
    system_state.set_mode(
        mode=SystemMode.RECOVERING,
        stage=RecoveryStage.CONNECT_BROKER,
        reason=ReasonCode.COLD_START
    )
    await recovery_orchestrator.run()
```

### 2.4 Force Override (上帝模式)

人工强制覆盖自动逻辑:

```python
async def force_mode(
    mode: SystemMode,
    ttl_seconds: int,
    operator_id: str,
    reason: str
) -> None:
    """
    Force system into specific mode, overriding automatic logic.

    Args:
        mode: Target mode (NORMAL, SAFE_MODE, HALT)
        ttl_seconds: Override duration (e.g., 300 = 5 minutes)
        operator_id: Who initiated the override
        reason: Human-readable reason
    """
    # Record in audit log
    # Set mode with override flag
    # After TTL expires, resume automatic logic
```

场景: 系统误判 Market Data 延迟 (其实是交易所休市), 需要人工确认平仓。

### 2.5 EventBus (通道)

进程内: 回调/asyncio.Queue
跨进程: Redis Pub/Sub / NATS (未来扩展)

**Publish 行为定义 (关键):**

| 事件类型 | 队列满时行为 | 原因 |
|----------|-------------|------|
| Log/Audit | **Drop-on-Full** + 本地计数器 | 不能阻塞交易 |
| Alert | **Drop-on-Full** + 写本地磁盘 | 不能阻塞交易 |
| Critical State Change | **必须送达** → 本地立刻降级 | 安全优先 |

```python
class EventBus:
    async def publish(self, event: SystemEvent) -> bool:
        """Non-blocking publish. Returns False if dropped."""
        try:
            # 必须用 put_nowait, 绝不阻塞
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._drop_count += 1
            if event.is_critical():
                # Critical 事件必须保证效果
                self._local_emergency_degrade(event)
            else:
                # 非 critical 事件丢弃并记录
                self._write_local_fallback_log("EventBus Full", event)
            return False
```

**"遗言"机制**: 如果 EventBus 自身挂了:
```python
class LocalBreaker:
    async def report_event(self, event: SystemEvent):
        try:
            await self._event_bus.publish(event)
        except EventBusError:
            # Fallback: 本地直接执行降级
            self._local_emergency_degrade()
            # 写本地磁盘日志
            self._write_local_fallback_log("EventBus Dead", event)
```

### 2.6 Local Breakers (分布)

每个组件独立管理:
- 错误分类、重试、退避
- 缓冲、只读、静默失败
- 上报标准化 `SystemEvent` 给中心

**关键规则: Local can only tighten (只能收紧, 不能放宽)**

```python
# 例如: SystemMode=DEGRADED 允许 open(受限)
# 但如果 risk breaker TRIPPED, 该组件仍必须拒绝
def can_execute(self, action: Action) -> bool:
    global_allowed = trading_gate.allows(action)
    local_allowed = not self._breaker.is_tripped()
    return global_allowed and local_allowed  # AND logic
```

### 2.7 TradingGate (统一门禁)

所有下单相关调用必须过 gate:
- `send_order()`, `amend_order()`, `cancel_order()`, `open_position()`
- Gate 只读中心 `SystemMode` (O(1) 本地读)

**Race Condition 处理**:

```python
# 方案: Double Check at execution layer
class BrokerAdapter:
    async def send_order(self, order: Order) -> OrderResult:
        # 最底层再 check 一次
        if not trading_gate.allows(ActionType.SEND):
            raise TradingHaltedError("System mode changed")

        try:
            return await self._broker.send(order)
        except NetworkError as e:
            # 捕获最后的失败, 触发降级
            await self._report_broker_failure(e)
            raise
```

**设计决策**: 接受毫秒级延迟, 依赖 Broker 层的 Exception Handler 捕获最后的失败。

---

## 3. Decision Matrix (决策矩阵)

### 3.1 Mode Transition Rules

| 触发条件 | 目标 Mode | 原因代码 |
|----------|-----------|----------|
| BROKER_DISCONNECT | SAFE_MODE_DISCONNECTED | broker.disconnect |
| BROKER_DISCONNECT + 重连成功 | RECOVERING | broker.reconnected |
| MD_STALE > stale_threshold | SAFE_MODE | market_data.stale |
| RISK_TIMEOUT 连续 N 次 | SAFE_MODE | risk.timeout |
| POSITION_TRUTH_UNKNOWN | HALT | position.unknown |
| BROKER_REPORT_MISMATCH | HALT | broker.mismatch |
| RECOVERY_FAILED > max_attempts | HALT | recovery.failed |
| DB_WRITE_FAIL + WAL available | DEGRADED | db.write_fail_buffered |
| DB_WRITE_FAIL + WAL full | SAFE_MODE | db.buffer_overflow |
| ALERTS_CHANNEL_DOWN | DEGRADED | alerts.channel_down |
| MD_QUALITY_DEGRADED (容忍区间) | DEGRADED | market_data.quality_low |
| 所有探针 OK + 稳定 T 秒 | NORMAL | all.healthy |

### 3.2 Conflict Resolution (冲突合并规则)

**多事件同时发生时, 取最严重的 mode:**

```python
def resolve_target_mode(events: list[SystemEvent]) -> SystemMode:
    """
    当多个事件同时发生时, 选择优先级最高(最严重)的 mode.

    优先级: HALT > SAFE_MODE_DISCONNECTED > SAFE_MODE > RECOVERING > DEGRADED > NORMAL
    """
    target_modes = [decision_matrix.get_target(e.reason_code) for e in events]
    return max(target_modes, key=lambda m: MODE_PRIORITY[m])

# 硬规则: 进入更严重 mode 后, 不允许被较轻事件降回
def can_transition(current: SystemMode, target: SystemMode) -> bool:
    if MODE_PRIORITY[target] >= MODE_PRIORITY[current]:
        return True  # 可以升级或保持
    # 只有满足恢复条件才能降级
    return self._recovery_conditions_met(current, target)
```

**示例:**
- MD_STALE + DB_WRITE_FAIL + ALERTS_DOWN 同时发生
- 目标 modes: SAFE_MODE, DEGRADED, DEGRADED
- 结果: SAFE_MODE (取最严重)

### 3.3 Mode Permissions

| SystemMode | open | send | amend | cancel | reduce-only | query |
|------------|------|------|-------|--------|-------------|-------|
| NORMAL | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| DEGRADED | ✓(受限) | ✓ | ✓ | ✓ | ✓ | ✓ |
| SAFE_MODE | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| SAFE_MODE_DISCONNECTED | ✗ | ✗ | ✗ | ✗ | ✗ | ✓(本地) |
| HALT | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| RECOVERING | 按 stage | 按 stage | 按 stage | 按 stage | 按 stage | ✓ |

### 3.4 SAFE_MODE_DISCONNECTED Query Source

**本地缓存定义:**

| 数据类型 | 缓存来源 | 刷新策略 |
|----------|----------|----------|
| Positions | 最后一次 broker.get_positions() 成功响应 | 每次成功查询更新 |
| Market Data | 最后一笔有效 quote/bar | 每次收到更新 |
| Orders | 本地订单状态机 (可能不完整) | 实时更新 |

**一致性语义:**

```python
@dataclass
class CachedData:
    data: Any
    cached_at_wall: datetime      # 用于展示
    cached_at_mono: float         # 用于 stale 判断
    is_stale: bool = False        # 超过阈值自动标记

def get_positions_cached(self) -> CachedPositions:
    result = self._position_cache.get()
    result.is_stale = self._is_stale(result.cached_at_mono, threshold_ms=30000)
    return result
```

**UI 必须显示:**
- "Data may be stale" 警告
- 缓存时间戳
- 最后成功同步时间

---

## 4. Event Protocol

### 4.1 SystemEvent Structure (双时间戳)

```python
@dataclass
class SystemEvent:
    event_type: EventType       # FAIL_CRIT / FAIL_SUPP / RECOVERED / HEARTBEAT / QUALITY_DEGRADED
    source: ComponentSource     # broker / market_data / risk / db / alerts
    severity: Severity          # INFO / WARN / CRIT
    reason_code: ReasonCode     # BROKER_DISCONNECT, MD_STALE, RISK_TIMEOUT, etc.
    details: dict | None        # 扁平 JSON
    ttl_seconds: int | None     # 状态过期时间

    # 双时间戳 (关键)
    event_time_wall: datetime   # 用于审计/展示 (可能跳变)
    event_time_mono: float      # 用于滞回/TTL/stale 判断 (monotonic)

# 使用规则
# - 所有判断逻辑只用 event_time_mono
# - 所有展示/审计/日志用 event_time_wall
```

### 4.2 Hysteresis (滞回/去抖)

避免抖动:
- FAIL → UNSTABLE: 需要 N 次或持续 T 秒
- UNSTABLE → TRIPPED: 继续失败则触发
- RECOVERED → HEALTHY: 需要连续稳定 T 秒
- SAFE_MODE: 最小驻留时间, 不允许频繁抖回

**TTL 过期语义**:
```python
# 关键组件的坏状态过期后 → UNKNOWN (更保守)
# UNKNOWN 触发 DEGRADED 或更保守的 mode
if event.is_expired() and event.source.is_critical():
    return ComponentStatus.UNKNOWN  # 不是 HEALTHY
```

### 4.3 Time Semantics

**统一口径**:
- 所有滞回与 stale 判定使用 `monotonic clock` (event_time_mono)
- 所有展示/审计/日志使用 `wall clock` (event_time_wall)

```python
import time
from datetime import datetime, timezone

def create_event(...) -> SystemEvent:
    return SystemEvent(
        ...,
        event_time_wall=datetime.now(tz=timezone.utc),  # 展示用
        event_time_mono=time.monotonic(),                # 判断用
    )

def is_stale(last_mono: float, threshold_ms: int) -> bool:
    """Use monotonic time to avoid system clock jumps."""
    elapsed_ms = (time.monotonic() - last_mono) * 1000
    return elapsed_ms > threshold_ms
```

---

## 5. Recovery Orchestration

### 5.1 Recovery Stages

```python
class RecoveryStage(Enum):
    CONNECT_BROKER = "connect_broker"
    CATCHUP_MARKETDATA = "catchup_marketdata"
    VERIFY_RISK = "verify_risk"
    READY = "ready"
```

### 5.2 Stage Permissions

| Stage | query | cancel | reduce-only | open |
|-------|-------|--------|-------------|------|
| CONNECT_BROKER | ✓ | ✗ | ✗ | ✗ |
| CATCHUP_MARKETDATA | ✓ | ✗ | ✗ | ✗ |
| VERIFY_RISK | ✓ | ✓(如broker可用) | ✗ | ✗ |
| READY | ✓ | ✓ | ✓ | ✗ |
| READY + 稳定 T 秒 | → NORMAL | | | |

### 5.3 Stage Progression

```
COLD_START / SAFE_MODE / HALT
    │
    ▼ (trigger: auto after reconnect, or manual)
RECOVERING(CONNECT_BROKER)
    │ broker.ensure_connected() ✓
    ▼
RECOVERING(CATCHUP_MARKETDATA)
    │ market_data.is_fresh() ✓
    ▼
RECOVERING(VERIFY_RISK)
    │ risk.self_check() ✓
    │ position.reconcile() ✓
    ▼
RECOVERING(READY)
    │ all checks pass for T seconds
    ▼
NORMAL
```

### 5.4 Recovery Triggers & Idempotency

**recovery_run_id 机制 (防止并发恢复):**

```python
class RecoveryOrchestrator:
    def __init__(self):
        self._current_run_id: str | None = None
        self._lock = asyncio.Lock()

    async def start_recovery(
        self,
        trigger: RecoveryTrigger,  # AUTO / MANUAL
        operator_id: str | None = None,
    ) -> str:
        """
        Start recovery. Returns run_id.

        Idempotent: new recovery replaces/cancels existing one.
        """
        async with self._lock:
            if self._current_run_id:
                await self._cancel_current()

            self._current_run_id = f"recovery-{uuid4().hex[:8]}"
            # ... start stages
            return self._current_run_id
```

| 触发方式 | 条件 | operator_id | READY → NORMAL |
|----------|------|-------------|----------------|
| AUTO | CRIT 故障恢复后 | None | 默认自动 (auto_recovery_to_normal=True) |
| MANUAL | 运维调用 API | 必须提供 | 按配置 |
| FORCE | force_mode(NORMAL, ttl) | 必须提供 | 立即, 但有 TTL |

**默认配置:**
```python
auto_recovery_to_normal: bool = True  # READY 稳定后自动进入 NORMAL
# 除非你们 oncall 资源很强, 否则建议 True
```

Stage 失败则:
- 回退到 SAFE_MODE / HALT
- 发出 alert (Slice 3.1)
- 记录 audit (Slice 3.2)

---

## 6. DB Buffering

### 6.1 Buffer Constraints

```python
@dataclass
class DBBufferConfig:
    # 主限制 (推荐)
    max_entries: int = 1000         # 最大条数

    # 辅助限制 (基于序列化后大小)
    max_bytes: int = 10_000_000     # 10MB (json.dumps 后的长度)
    max_seconds: float = 60.0       # 最大缓冲时间
```

**内存爆炸防护:**
```python
def add_to_buffer(self, entry: BufferEntry) -> bool:
    # 用序列化后大小计算, 避免 Python 对象开销误判
    serialized = json.dumps(entry.to_dict())
    entry_bytes = len(serialized.encode('utf-8'))

    if self._current_entries >= self._config.max_entries:
        return False
    if self._current_bytes + entry_bytes >= self._config.max_bytes:
        return False

    self._buffer.append(entry)
    self._current_entries += 1
    self._current_bytes += entry_bytes
    return True
```

### 6.2 WAL 落盘策略

**关键状态变更必须落盘:**

```python
class WALWriter:
    def __init__(self, wal_path: Path):
        self._wal_path = wal_path
        self._file = open(wal_path, 'ab')  # append binary

    def write(self, entry: WALEntry) -> None:
        """
        Sync write to disk. Critical entries must survive power loss.
        """
        # 幂等 key 用于重放去重
        entry.idempotent_key = f"{entry.resource_type}:{entry.resource_id}:{entry.seq_no}"

        line = json.dumps(entry.to_dict()) + '\n'
        self._file.write(line.encode('utf-8'))
        self._file.flush()
        os.fsync(self._file.fileno())  # 确保落盘
```

**Flush 幂等性:**
```python
async def flush_wal_to_db(self):
    """Replay WAL entries to DB with idempotent key dedup."""
    for entry in self._read_wal():
        # 使用 ON CONFLICT DO NOTHING 或者先查后插
        await self._db.execute(
            """
            INSERT INTO state_changes (idempotent_key, ...)
            VALUES (:key, ...)
            ON CONFLICT (idempotent_key) DO NOTHING
            """,
            {"key": entry.idempotent_key, ...}
        )
    # 清空 WAL
    self._truncate_wal()
```

### 6.3 Overflow Handling

```python
async def on_buffer_overflow():
    """Buffer exceeded limits."""
    # 1. 升级到 SAFE_MODE
    await system_state.transition(
        mode=SystemMode.SAFE_MODE,
        reason=ReasonCode.DB_BUFFER_OVERFLOW
    )

    # 2. 拒绝新单 (不是丢弃已缓冲的)
    # 3. 尝试 flush (如果 DB 恢复)
    # 4. 超过 max_seconds 仍无法写入 → HALT
```

---

## 7. Integration with Slice 3.1/3.2

### 7.1 Alert Integration (Slice 3.1)

每次 SystemMode 变化:
```python
alert_service.emit(
    alert_type=AlertType.SYSTEM_MODE_CHANGE,
    severity=Severity.WARNING if new_mode in (DEGRADED, SAFE_MODE) else Severity.CRITICAL,
    summary=f"System mode changed: {old_mode} → {new_mode}",
    details={"reason": reason_code, "source": source}
)
```

### 7.2 Audit Integration (Slice 3.2)

每次 mode 变化:
```python
audit_service.log(
    event_type=AuditEventType.SYSTEM_MODE_CHANGED,
    resource_type=ResourceType.SYSTEM,
    resource_id="trading-system",
    old_value={"mode": old_mode},
    new_value={"mode": new_mode, "reason": reason_code}
)
```

**关键**: 写失败不阻塞 Hot Path (异步队列/WAL)

---

## 8. Component Probe Interface

每个 Hot Path 组件提供探针接口:

```python
class ComponentProbe(Protocol):
    async def health_check(self) -> HealthSignal:
        """Quick health check for recovery orchestration."""
        ...

    async def ensure_ready(self) -> bool:
        """Attempt to restore ready state. Return success."""
        ...

    def get_status(self) -> ComponentStatus:
        """Current status snapshot."""
        ...

    def get_last_update_mono(self) -> float:
        """Monotonic timestamp of last successful update."""
        ...
```

---

## 9. Configuration

```python
@dataclass
class DegradationConfig:
    # Hysteresis
    fail_threshold_count: int = 3           # N failures before UNSTABLE
    fail_threshold_seconds: float = 5.0     # or T seconds of failures
    recovery_stable_seconds: float = 10.0   # stable for T seconds before NORMAL
    min_safe_mode_seconds: float = 30.0     # minimum time in SAFE_MODE
    unknown_on_ttl_expiry: bool = True      # TTL expired → UNKNOWN (not HEALTHY)
    alert_on_unstable: bool = True          # Send WARNING alert on UNSTABLE

    # Timeouts
    broker_timeout_ms: int = 5000
    market_data_stale_ms: int = 10000
    risk_timeout_ms: int = 2000
    db_timeout_ms: int = 3000

    # Recovery
    max_recovery_attempts: int = 3
    recovery_backoff_base_ms: int = 1000
    auto_recovery_to_normal: bool = True    # READY 稳定后自动进入 NORMAL

    # DB Buffer
    db_buffer_max_entries: int = 1000       # 主限制
    db_buffer_max_bytes: int = 10_000_000   # 基于 json.dumps 后的大小
    db_buffer_max_seconds: float = 60.0
    db_wal_enabled: bool = True             # 关键状态落盘

    # EventBus
    event_bus_queue_size: int = 10000
    event_bus_publish_timeout_ms: int = 100
    event_bus_drop_on_full: bool = True     # 非 critical 事件丢弃

    # Cache staleness
    position_cache_stale_ms: int = 30000
    market_data_cache_stale_ms: int = 10000
```

---

## 10. Implementation Constraints (工程约束)

1. **Single Writer**: SystemState 只能由 SystemStateService 修改
2. **Non-blocking**: EventBus publish 必须是 nowait, 绝不阻塞 Trading Loop
3. **Monotonic Time**: 所有滞回与 stale 判定使用 event_time_mono
4. **Wall Time for Display**: 所有展示/审计/日志使用 event_time_wall
5. **Local Can Only Tighten**: 组件本地权限只能比 Gate 更保守
6. **Mode Change Must Have**: reason_code + source + event_time_wall + event_time_mono
7. **Double Check**: 执行层 (Broker) 在实际发单前再检查一次 SystemMode
8. **Fallback on Bus Failure**: EventBus 不可用时本地直接降级 + 写磁盘日志
9. **Drop-on-Full**: 非 critical 事件队列满时丢弃, 不阻塞
10. **WAL for Critical**: 关键状态变更必须落盘, 使用幂等 key 去重
11. **Conflict Resolution**: 多事件取最严重 mode, 不允许被较轻事件降回
12. **Recovery Idempotent**: recovery_run_id 确保新恢复替换旧恢复

---

## 11. Files to Create

### Backend

| File | Purpose |
|------|---------|
| `src/degradation/__init__.py` | Module exports |
| `src/degradation/models.py` | SystemMode, SystemLevel, RecoveryStage, SystemEvent, enums |
| `src/degradation/config.py` | DegradationConfig, thresholds |
| `src/degradation/state_service.py` | SystemStateService (central) with force_mode |
| `src/degradation/event_bus.py` | EventBus with drop-on-full and fallback |
| `src/degradation/trading_gate.py` | TradingGate (unified gate) |
| `src/degradation/breakers.py` | CircuitBreaker base + component breakers |
| `src/degradation/recovery.py` | RecoveryOrchestrator with run_id |
| `src/degradation/probes.py` | ComponentProbe protocol + implementations |
| `src/degradation/db_buffer.py` | DB write buffer with WAL |
| `src/degradation/cache.py` | CachedData with staleness tracking |
| `src/degradation/setup.py` | init_degradation_service, get_system_state |
| `src/api/degradation.py` | API endpoints including force_mode |

### Frontend

| File | Purpose |
|------|---------|
| `src/types/index.ts` | SystemMode, SystemLevel, RecoveryStage types |
| `src/api/degradation.ts` | API client |
| `src/hooks/useDegradation.ts` | React hooks |
| `src/components/SystemStatus.tsx` | Status indicator + stale warning |
| `src/components/RecoveryPanel.tsx` | Recovery controls + force override |
| `src/pages/SystemPage.tsx` | System status page |

### Tests

| File | Purpose |
|------|---------|
| `tests/degradation/test_models.py` | Model tests |
| `tests/degradation/test_state_service.py` | State machine + decision matrix + conflict resolution |
| `tests/degradation/test_trading_gate.py` | Gate permission tests |
| `tests/degradation/test_breakers.py` | Circuit breaker + hysteresis tests |
| `tests/degradation/test_recovery.py` | Recovery orchestration + idempotency tests |
| `tests/degradation/test_db_buffer.py` | Buffer limit + WAL tests |
| `tests/degradation/test_event_bus.py` | Drop-on-full + fallback tests |
| `tests/degradation/test_integration.py` | End-to-end tests |

---

## 12. Implementation-Level Safeguards (实现级硬点)

### 12.1 Must-Deliver Event Whitelist

**精确定义 "Critical" 事件:**

```python
# 只有这些事件才标记为 is_critical=True
MUST_DELIVER_EVENTS = frozenset({
    ReasonCode.BROKER_DISCONNECT,
    ReasonCode.POSITION_TRUTH_UNKNOWN,
    ReasonCode.BROKER_REPORT_MISMATCH,
    ReasonCode.RISK_BREACH_HARD,
})

def is_critical(self) -> bool:
    """Only whitelist events are critical."""
    return self.reason_code in MUST_DELIVER_EVENTS
```

**规则:**
- 只有白名单内的事件才会触发本地兜底降级
- Alert/Audit/Metric 永远不是 critical (drop-on-full)
- 新增 critical 事件需要代码审查

### 12.2 SAFE_MODE Cancel Boundary Conditions

**SAFE_MODE 下 cancel 是 "best-effort":**

```python
class TradingGate:
    def allows_cancel(self) -> tuple[bool, str | None]:
        """
        Returns (allowed, warning_message).

        In SAFE_MODE, cancel is allowed but best-effort.
        """
        if self._mode == SystemMode.SAFE_MODE:
            return (True, "SAFE_MODE: Cancel is best-effort, may fail")
        if self._mode == SystemMode.SAFE_MODE_DISCONNECTED:
            return (False, "DISCONNECTED: Cancel not possible, no broker connection")
        if self._mode == SystemMode.HALT:
            return (False, "HALT: All operations suspended")
        return (True, None)
```

**UI 必须显示:**
- SAFE_MODE 下 cancel 按钮显示 ⚠️ "Best Effort"
- SAFE_MODE_DISCONNECTED 下 cancel 按钮 disabled + tooltip 说明
- 失败后清晰的错误信息而非静默失败

### 12.3 Decision Matrix Config Binding

**所有阈值必须来自 config, 不允许硬编码:**

```python
class DecisionMatrix:
    def __init__(self, config: DegradationConfig):
        self._config = config

        # 从 config 读取, 不硬编码
        self._stale_threshold_ms = config.market_data_stale_ms
        self._risk_timeout_threshold = config.risk_timeout_consecutive_count

    def get_target_mode(self, reason_code: ReasonCode, context: EventContext) -> SystemMode:
        """All thresholds come from config, not hardcoded."""
        match reason_code:
            case ReasonCode.MD_STALE:
                if context.stale_duration_ms > self._config.market_data_stale_ms:
                    return SystemMode.SAFE_MODE
            case ReasonCode.RISK_TIMEOUT:
                if context.consecutive_failures >= self._config.risk_timeout_consecutive_count:
                    return SystemMode.SAFE_MODE
        # ...
```

**禁止:**
```python
# ❌ 禁止硬编码
if stale_ms > 10000:  # 不允许

# ✅ 必须从 config 读取
if stale_ms > self._config.market_data_stale_ms:
```

### 12.4 WAL Replay Idempotency Boundary

**WAL 只存储状态, 不重放外部动作:**

```python
class WALEntry:
    """
    WAL entries represent STATE CHANGES, not ACTIONS.

    ✅ Record: "Order X transitioned to state CANCELLED"
    ❌ Don't Record: "Send cancel request to broker for order X"
    """
    resource_type: str
    resource_id: str
    old_state: dict | None
    new_state: dict
    idempotent_key: str  # For dedup on replay

# WAL 重放时只更新本地状态, 不触发外部调用
async def replay_wal_entry(self, entry: WALEntry):
    """
    Replay restores LOCAL state only.
    Does NOT re-send broker commands.
    Does NOT re-emit alerts.
    """
    # 只更新 DB 状态
    await self._db.execute(
        """
        INSERT INTO state_changes (idempotent_key, resource_type, resource_id, new_state, ...)
        VALUES (:key, :type, :id, :state, ...)
        ON CONFLICT (idempotent_key) DO NOTHING
        """,
        entry.to_params()
    )
    # 不调用 broker.cancel(), alert_service.emit(), etc.
```

**幂等边界:**
- WAL 是 "状态快照的重放", 不是 "动作的重放"
- 外部系统状态 (broker orders) 以 broker 返回为准, 不以 WAL 为准
- WAL 重放只用于恢复本地 DB 一致性

---

## 13. Exit Criteria

### Core Architecture
- [ ] SystemStateService 管理 6 种模式 + 3 种 level 状态机
- [ ] MODE_PRIORITY 定义冲突合并规则, 取最严重 mode
- [ ] SystemLevel UNSTABLE 不改变 mode, 只发 warning alert
- [ ] Cold Start: 启动时进入 RECOVERING
- [ ] Force Override: 支持人工强制设定 mode + TTL

### Trading Gate & Breakers
- [ ] TradingGate 根据 mode + stage 控制交易权限
- [ ] Circuit Breakers 为 Broker/MarketData/Risk/DB, 支持 UNSTABLE/TRIPPED
- [ ] 滞回机制防止状态抖动 (fail_threshold + recovery_stable)
- [ ] TTL 过期 → UNKNOWN (不是 HEALTHY)

### Event & Time Handling
- [ ] 双时间戳: event_time_wall (展示) + event_time_mono (判断)
- [ ] EventBus nowait + drop-on-full (非 critical)
- [ ] EventBus 失败时本地兜底降级

### Recovery
- [ ] Recovery 编排 4 个阶段, 按阶段放行权限
- [ ] recovery_run_id 确保恢复流程幂等

### DB & Persistence
- [ ] DB Buffer 有上限 (max_entries 为主), 基于 json.dumps 大小
- [ ] WAL 落盘关键状态, 使用幂等 key 去重
- [ ] WAL 只存储状态变更, 不重放外部动作

### Integration & UI
- [ ] SAFE_MODE_DISCONNECTED 查询本地缓存, UI 显示 stale 警告
- [ ] SAFE_MODE cancel 显示 "best-effort" 警告
- [ ] Mode 变化触发 Alert + Audit (异步)
- [ ] Dashboard 显示系统状态 + Level + stale 警告 + 恢复控制 + Force Override

### Safety Invariants
- [ ] 所有组件异常不阻塞 Trading Hot Path
- [ ] Decision Matrix 作为唯一判定依据实现, 阈值从 config 读取
- [ ] MUST_DELIVER_EVENTS 白名单精确定义 critical 事件
- [ ] 所有 Decision Matrix 阈值禁止硬编码
