# Greeks Monitoring V2 - 设计文档

**版本**: 2.0
**创建日期**: 2026-01-31
**状态**: 已审核 (Human Override)

---

## 1. 概述

### 1.1 V2 目标

基于 V1/V1.5 Greeks 监控系统，扩展以下功能：

| 功能 | 描述 |
|------|------|
| Pre-order 限额检查 | 下单前校验 Greeks 限额，超限阻断信号 |
| Scenario Shock API | ±1%/±2% 情景分析，返回 PnL + New Delta |
| PUT /limits | 通过 API 动态更新限额配置 |
| GET /history | 历史 Greeks 查询，支持 1h/4h/1d/7d 窗口 |

### 1.2 审核记录

| 功能 | Codex | Gemini | 决策 |
|------|-------|--------|------|
| Pre-order 限额检查 | BLOCKED | FAIL | Human Override ✅ |
| Scenario Shock API | BLOCKED | FAIL | Human Override ✅ |
| PUT /limits (theta ABS) | PASS | PASS | 采纳 ✅ |
| GET /history | BLOCKED | FAIL | Human Override ✅ |

---

## 2. Pre-order Greeks 限额检查

### 2.1 架构

```
Signal → RiskManager.evaluate()
              ↓
         _check_kill_switch()
         _check_strategy_paused()
         _check_symbol_allowed()
         _check_position_limits()
         _check_portfolio_limits()
         _check_loss_limits()
    NEW: _check_greeks_limits()  ←── V2
              ↓
         RiskResult(approved=True/False)
```

### 2.2 数据模型

```python
@dataclass
class OrderIntent:
    """下单意图，支持 multi-leg"""
    account_id: str
    strategy_id: str | None
    legs: list[OrderLeg]

@dataclass
class OrderLeg:
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    contract_type: Literal["call", "put", "stock"]
    strike: Decimal | None
    expiry: date | None
    multiplier: int = 100

@dataclass
class GreeksCheckResult:
    """结构化返回，支持审计"""
    ok: bool
    reason_code: str  # APPROVED | HARD_BREACH | DATA_UNAVAILABLE | DATA_STALE
    details: GreeksCheckDetails | None

@dataclass
class GreeksCheckDetails:
    asof_ts: datetime
    staleness_seconds: int
    current: dict[str, Decimal]      # {delta, gamma, vega, theta}
    impact: dict[str, Decimal]       # 订单影响
    projected: dict[str, Decimal]    # current + impact
    limits: dict[str, Decimal]       # hard limits
    breach_dims: list[str]           # ["delta", "gamma"] 超限维度
```

### 2.3 核心逻辑

```python
class RiskManager:
    def __init__(
        self,
        ...,
        greeks_monitor: GreeksMonitor | None = None,
        greeks_calculator: GreeksCalculator | None = None,
        greeks_check_config: GreeksCheckConfig | None = None,
    ):
        self._greeks_monitor = greeks_monitor
        self._greeks_calculator = greeks_calculator
        self._greeks_config = greeks_check_config or GreeksCheckConfig()

    async def _check_greeks_limits(
        self, order: OrderIntent
    ) -> GreeksCheckResult:
        # 1. 获取当前 Greeks + 时效检查
        current = await self._greeks_monitor.get_current_greeks(
            order.account_id
        )
        if current is None:
            return self._handle_data_unavailable()

        staleness = (now() - current.asof_ts).total_seconds()
        if staleness > self._greeks_config.max_staleness_seconds:
            return self._handle_data_stale(staleness)

        # 2. 计算订单 legs 的 Greeks 影响（调用 calculator）
        impact = await self._calculate_order_impact(order)

        # 3. 投影 = 当前 + 影响
        projected = {
            greek: current[greek] + impact[greek]
            for greek in ["delta", "gamma", "vega", "theta"]
        }

        # 4. 检查 HARD 限额（abs 比较）
        breach_dims = [
            greek for greek, value in projected.items()
            if abs(value) > self._greeks_config.hard_limits[greek]
        ]

        return GreeksCheckResult(
            ok=len(breach_dims) == 0,
            reason_code="APPROVED" if not breach_dims else "HARD_BREACH",
            details=GreeksCheckDetails(
                asof_ts=current.asof_ts,
                staleness_seconds=int(staleness),
                current=current.as_dict(),
                impact=impact,
                projected=projected,
                limits=self._greeks_config.hard_limits,
                breach_dims=breach_dims,
            ),
        )

    def _handle_data_unavailable(self) -> GreeksCheckResult:
        """Fail-closed: 数据不可用时阻断"""
        logger.critical("[RISK_BLOCK] Greeks data unavailable")
        return GreeksCheckResult(
            ok=False,
            reason_code="DATA_UNAVAILABLE",
            details=None,
        )

    def _handle_data_stale(self, staleness: float) -> GreeksCheckResult:
        """Fail-closed: 数据过期时阻断"""
        logger.warning(f"[RISK_BLOCK] Greeks stale: {staleness}s")
        return GreeksCheckResult(
            ok=False,
            reason_code="DATA_STALE",
            details=None,
        )
```

### 2.4 配置

```python
@dataclass
class GreeksCheckConfig:
    max_staleness_seconds: int = 60
    fail_mode: Literal["closed", "open"] = "closed"
    hard_limits: dict[str, Decimal] = field(default_factory=lambda: {
        "delta": Decimal("200000"),
        "gamma": Decimal("10000"),
        "vega": Decimal("40000"),
        "theta": Decimal("6000"),
    })
```

### 2.5 关键约束

| 约束 | 设计 |
|------|------|
| 入参 | `OrderIntent` + `OrderLeg[]` 支持 multi-leg |
| Greeks 计算 | 4 个 Greeks 全算，调用 `GreeksCalculator` |
| Fail 策略 | 默认 **fail-closed** |
| 数据时效 | `asof_ts` + `max_staleness_seconds` 检查 |
| 比较规则 | `abs(value) > hard_limit` |
| 返回值 | `GreeksCheckResult` 结构化，含 `breach_dims` |

---

## 3. Scenario Shock API

### 3.1 端点

```
GET /api/greeks/accounts/{account_id}/scenario
    ?shocks=1,2       # 可选，默认 1,2 (±1%, ±2%)
    ?scope=account    # account | strategy
    ?strategy_id=xxx  # 当 scope=strategy 时必填
```

### 3.2 响应模型

```python
@dataclass
class ScenarioShockResponse:
    account_id: str
    scope: Literal["account", "strategy"]
    scope_id: str | None
    asof_ts: datetime
    current: CurrentGreeks
    scenarios: dict[str, ScenarioResult]

@dataclass
class CurrentGreeks:
    ref_spot: Decimal              # 基准标的价格
    dollar_delta: Decimal          # dP/dS
    gamma: Decimal                 # d²P/dS²
    gamma_pnl_1pct: Decimal        # 1% shock 的 gamma PnL
    vega_per_1pct: Decimal
    theta_per_day: Decimal
    delta_pnl_1pct: Decimal        # = dollar_delta * ref_spot * 0.01

@dataclass
class ScenarioResult:
    shock_pct: Decimal
    direction: Literal["up", "down"]
    pnl_from_delta: Decimal        # 一阶项（带方向）
    pnl_from_gamma: Decimal        # 二阶项（不随方向变）
    pnl_impact: Decimal            # = pnl_from_delta + pnl_from_gamma
    ref_spot: Decimal
    delta_spot: Decimal            # = ref_spot * shock_pct% * sign
    new_delta: Decimal
    delta_change: Decimal          # = gamma * delta_spot
    breach_level: Literal["none", "warn", "crit", "hard"]
    breach_dims: list[str]
```

### 3.3 计算公式

```python
def calculate_scenario(
    current: CurrentGreeks,
    shock_pct: Decimal,
    direction: Literal["up", "down"],
    limits: LimitConfig,
) -> ScenarioResult:
    sign = Decimal("1") if direction == "up" else Decimal("-1")
    shock = shock_pct / Decimal("100")

    # ΔS = S × shock × sign
    delta_spot = current.ref_spot * shock * sign

    # 一阶项：PnL_delta = dollar_delta × ΔS
    pnl_from_delta = current.dollar_delta * delta_spot

    # 二阶项：PnL_gamma = gamma_pnl_1pct × (shock_pct)²（不乘 sign）
    scale = (shock_pct / Decimal("1")) ** 2
    pnl_from_gamma = current.gamma_pnl_1pct * scale

    # 总 PnL
    pnl_impact = pnl_from_delta + pnl_from_gamma

    # Delta 变化
    delta_change = current.gamma * delta_spot
    new_delta = current.dollar_delta + delta_change

    # 检查限额
    breach_level, breach_dims = check_breach(new_delta, limits)

    return ScenarioResult(...)
```

### 3.4 示例响应

```json
{
  "account_id": "ACC001",
  "scope": "account",
  "scope_id": null,
  "asof_ts": "2026-01-31T10:30:00Z",
  "current": {
    "ref_spot": 150.00,
    "dollar_delta": 500,
    "gamma": 20,
    "gamma_pnl_1pct": 225,
    "vega_per_1pct": 15000,
    "theta_per_day": -2800,
    "delta_pnl_1pct": 750
  },
  "scenarios": {
    "+1%": {
      "shock_pct": 1,
      "direction": "up",
      "pnl_from_delta": 750,
      "pnl_from_gamma": 225,
      "pnl_impact": 975,
      "ref_spot": 150.00,
      "delta_spot": 1.50,
      "new_delta": 530,
      "delta_change": 30,
      "breach_level": "none",
      "breach_dims": []
    },
    "-1%": {
      "shock_pct": 1,
      "direction": "down",
      "pnl_from_delta": -750,
      "pnl_from_gamma": 225,
      "pnl_impact": -525,
      "ref_spot": 150.00,
      "delta_spot": -1.50,
      "new_delta": 470,
      "delta_change": -30,
      "breach_level": "none",
      "breach_dims": []
    }
  }
}
```

---

## 4. PUT /limits 端点

### 4.1 端点

```
PUT /api/greeks/accounts/{account_id}/limits
```

### 4.2 请求模型

```python
@dataclass
class GreeksLimitsRequest:
    account_id: str
    strategy_id: str | None = None  # V2 返回 501
    limits: GreeksLimitSet

@dataclass
class GreeksLimitSet:
    delta: ThresholdLevels
    gamma: ThresholdLevels
    vega: ThresholdLevels
    theta: ThresholdLevels

@dataclass
class ThresholdLevels:
    warn: Decimal
    crit: Decimal
    hard: Decimal
```

### 4.3 响应模型

```python
@dataclass
class GreeksLimitsResponse:
    account_id: str
    strategy_id: str | None
    limits: GreeksLimitSet
    updated_at: datetime
    updated_by: str
    effective_scope: Literal["account", "strategy"]
```

### 4.4 验证规则

```python
def validate_limits(limits: GreeksLimitSet) -> list[str]:
    errors = []
    for greek in ["delta", "gamma", "vega", "theta"]:
        levels = getattr(limits, greek)
        # 所有 Greeks 统一规则：0 < warn < crit < hard
        if not (0 < levels.warn < levels.crit < levels.hard):
            errors.append(f"{greek}: must satisfy 0 < warn < crit < hard")
    return errors
```

### 4.5 评估方式

所有 Greeks（包括 theta）使用 **ABS 评估**：

```python
# 评估时
for greek in ["delta", "gamma", "vega", "theta"]:
    if abs(current_value) > limits[greek].hard:
        # 触发 HARD 告警
```

### 4.6 存储

- **Redis**: 热配置读取
- **DB**: 审计历史 (`greeks_limits_history` 表)
- **双写**: 先 DB 后 Redis
- **通知**: `AlertEngine.reload_limits()` 重新加载

### 4.7 示例

**Request:**
```json
{
  "account_id": "ACC001",
  "limits": {
    "delta": {"warn": 100000, "crit": 150000, "hard": 200000},
    "gamma": {"warn": 5000, "crit": 7500, "hard": 10000},
    "vega": {"warn": 20000, "crit": 30000, "hard": 40000},
    "theta": {"warn": 3000, "crit": 4500, "hard": 6000}
  }
}
```

**Response:**
```json
{
  "account_id": "ACC001",
  "strategy_id": null,
  "limits": {...},
  "updated_at": "2026-01-31T10:30:00Z",
  "updated_by": "user_123",
  "effective_scope": "account"
}
```

---

## 5. GET /history 端点

### 5.1 端点

```
GET /api/greeks/accounts/{account_id}/history
    ?window=1h|4h|1d|7d
    ?scope=account
    ?strategy_id=xxx
```

### 5.2 自动聚合规则

| 窗口 | 原始间隔 | 聚合粒度 | 预计点数 |
|------|----------|----------|----------|
| 1h | 30s | 原始 | ~120 |
| 4h | 30s | 1min | ~240 |
| 1d | 30s | 5min | ~288 |
| 7d | 30s | 1h | ~168 |

### 5.3 响应模型

```python
@dataclass
class GreeksHistoryResponse:
    account_id: str
    scope: Literal["account", "strategy"]
    scope_id: str | None
    window: str
    interval: str
    start_ts: datetime
    end_ts: datetime
    points: list[GreeksHistoryPoint]

@dataclass
class GreeksHistoryPoint:
    ts: datetime
    dollar_delta: Decimal
    gamma_dollar: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal
    coverage_pct: Decimal
    point_count: int = 1
```

### 5.4 查询实现

```python
# TimescaleDB time_bucket 聚合
query = f"""
    SELECT
        time_bucket('{interval_sql}', as_of_ts) AS ts,
        AVG(dollar_delta) AS dollar_delta,
        AVG(gamma_dollar) AS gamma_dollar,
        AVG(vega_per_1pct) AS vega_per_1pct,
        AVG(theta_per_day) AS theta_per_day,
        AVG(coverage_pct) AS coverage_pct,
        COUNT(*) AS point_count
    FROM greeks_snapshots
    WHERE scope = $1
      AND scope_id = $2
      AND as_of_ts >= $3
      AND as_of_ts <= $4
    GROUP BY ts
    ORDER BY ts ASC
"""
```

### 5.5 示例响应

```json
{
  "account_id": "ACC001",
  "scope": "account",
  "scope_id": null,
  "window": "4h",
  "interval": "1m",
  "start_ts": "2026-01-31T06:30:00Z",
  "end_ts": "2026-01-31T10:30:00Z",
  "points": [
    {
      "ts": "2026-01-31T06:30:00Z",
      "dollar_delta": 72500,
      "gamma_dollar": 2400,
      "vega_per_1pct": 14800,
      "theta_per_day": -2750,
      "coverage_pct": 98.5,
      "point_count": 2
    }
  ]
}
```

---

## 6. 实施计划

### 6.1 任务分解

| Phase | 任务 | 文件 |
|-------|------|------|
| 1 | Pre-order Greeks Check | `backend/src/risk/manager.py`, `backend/src/risk/greeks_gate.py` |
| 2 | Scenario Shock API | `backend/src/api/greeks.py`, `backend/src/greeks/scenario.py` |
| 3 | PUT /limits | `backend/src/api/greeks.py`, `backend/src/greeks/limits_store.py` |
| 4 | GET /history | `backend/src/api/greeks.py`, `backend/src/greeks/repository.py` |
| 5 | 测试 | `backend/tests/greeks/test_v2_*.py` |

### 6.2 依赖

- V1/V1.5 Greeks Monitoring（已完成，PR #26）
- `GreeksMonitor.get_current_greeks()` 方法
- `GreeksCalculator` 单腿 Greeks 计算
- `greeks_snapshots` TimescaleDB 表

---

## 7. 附录：审核决策记录

### 7.1 Human Override 决策

| 时间 | 功能 | Reviewer | 意见 | 决策 | 理由 |
|------|------|----------|------|------|------|
| 2026-01-31 | Pre-order check | Codex | BLOCKED (Phase 3) | Override | V1 已合并，继续 V2 |
| 2026-01-31 | Pre-order check | Gemini | FAIL (Over-design) | Override | Multi-leg 是必需功能 |
| 2026-01-31 | Scenario Shock | Gemini | FAIL (new_delta over-design) | Override | 用户明确要求 PnL+Delta |
| 2026-01-31 | GET /history | Gemini | FAIL (1d/7d scope creep) | Override | V2 scope 包含长历史 |

### 7.2 采纳的 Reviewer 建议

| 功能 | 建议来源 | 内容 | 状态 |
|------|----------|------|------|
| Pre-order | User | Fail-closed 默认 | ✅ 采纳 |
| Pre-order | User | 结构化 GreeksCheckResult | ✅ 采纳 |
| Scenario | User | Gamma 项不乘 sign | ✅ 采纳 |
| Scenario | User | 加入 ref_spot | ✅ 采纳 |
| PUT /limits | Codex | Theta 用 ABS 评估 | ✅ 采纳 |
