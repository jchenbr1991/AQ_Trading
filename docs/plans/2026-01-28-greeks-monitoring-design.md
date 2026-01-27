# Greeks Monitoring - 组合 Greeks 监控系统设计

**设计文档版本**: 1.0
**创建日期**: 2026-01-28
**状态**: 设计中

---

## 目录

1. [系统概览](#1-系统概览)
2. [数据模型设计](#2-数据模型设计)
3. [核心组件实现](#3-核心组件实现)（待续）
4. [API 设计](#4-api-设计)（待续）
5. [前端架构](#5-前端架构)（待续）
6. [实施计划](#6-实施计划)（待续）

---

## 1. 系统概览

### 1.1 功能目标

实现期权组合 Greeks 的**准实时**监控与风险预警系统，作为 Risk Manager 的扩展模块。

**V1 目标**：
- **准实时监控**（event-driven + 30s backstop）
- 计算并展示账户/策略级别的组合 **Dollar Greeks**（$Delta/$Theta/$Vega/$Gamma）
- 三级告警机制（WARN/CRIT/HARD）+ 变化率异常检测 + 回差解除
- Dashboard 展示 `as_of_ts` + `staleness_seconds`，明确数据新鲜度
- **CRIT/HARD 告警时自动保存持仓快照**（事后分析用）

**V1 Dashboard 交付边界**：
- Summary 卡片（account/strategy tabs 切换）
- Limits utilization 进度条 + 当前级别
- Recent alerts 列表
- Minimal trends（1h/4h 趋势图）
- Breakdown 视图（V1 先做 by strategy，underlying 留 V1.5）

**V2 目标**：
- 下单前 Greeks 限额检查（信号阻断）
- Contribution ranking（Top N 持仓贡献度）
- Scenario shock 情景分析（±1%/±2%）
- 更长历史窗口

### 1.2 核心架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Greeks Monitor Service                          │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│  │GreeksCalc    │  │GreeksAggr    │  │GreeksAlertEngine           │ │
│  │(单持仓计算)   │  │(组合聚合)     │  │ - level-scoped dedupe      │ │
│  │              │  │              │  │ - escalation-through       │ │
│  │              │  │              │  │ - THRESHOLD|RATE_OF_CHANGE │ │
│  │              │  │              │  │ - RECOVERED event          │ │
│  └──────────────┘  └──────────────┘  └────────────────────────────┘ │
│         ↑                 ↑                      ↑                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              Data Quality & State Layer                       │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐  │   │
│  │  │ IVCacheManager  │  │GreeksSnapshot   │  │AlertDedupe   │  │   │
│  │  │ (IV/利率缓存)    │  │Store (快照+时序) │  │Store (状态)   │  │   │
│  │  └─────────────────┘  └─────────────────┘  └──────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
        ↑                        ↓                      ↓
   MarketData                Portfolio              AlertSystem
   (Futu primary)            (Positions)            (Existing)
   (Model fallback)
```

### 1.3 数据流

```
1. 触发源
   ├── Position CRUD（创建/更新/删除持仓）
   ├── Order Fill / Partial Fill（订单成交）
   ├── Strategy Assignment Change（position.strategy_id 变更）
   ├── Corporate Action / Multiplier Change（via 定时兜底）
   └── Backstop Poll（30s 定时轮询）

2. Fetch + Normalize（取数 → 规范化）
   ├── 获取 per-position Greeks
   │   ├── Primary: Futu API
   │   └── Fallback: Model calc (BS + Bjerksund-Stensland)
   │                 └── 依赖 IVCacheManager 提供最近有效 IV
   │
   ├── Normalize units to canonical convention:
   │   ├── Theta: per-day（不是 per-year）
   │   ├── Vega: per 1% IV change
   │   └── Source 符号/单位统一转换
   │
   └── 输出统一结构:
       {
         value: float,
         source: "futu" | "model" | "cached",
         model: "futu" | "bs" | "bjerksund" | null,
         staleness_seconds: int,
         as_of_ts: datetime
       }

3. Sanity Check（数据质量校验 - Soft Check）
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ 宽松但必需的校验（标记 warning，不轻易剔除）            │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ • abs(delta) <= 1.2（给余量，含 deep ITM 美式）         │
   │  │ • abs(gamma/vega/theta) <= configurable_max_threshold   │
   │  │ • NaN / Inf 检测 → valid=false                         │
   │  │ • staleness_seconds <= max_staleness（如 300s）         │
   │  │ • source / model 字段一致性                             │
   │  └─────────────────────────────────────────────────────────┘
   │
   └── 输出：
       ├── valid=true + quality_warnings=[]  → 正常
       ├── valid=true + quality_warnings=[...] → 可用但有警告
       └── valid=false → 仅 NaN/Inf/严重异常才标记

4. Aggregate（组合聚合）
   │
   │  输出两套数据（防止剔除坏数据导致低估风险）：
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ computed_greeks（仅 valid=true 的 legs）                │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ Dollar Greeks 规范定义（Canonical Convention）          │
   │  │                                                         │
   │  │ dollar_delta    = Δ × S × multiplier                   │
   │  │                   单位: $ / $1 underlying move          │
   │  │                                                         │
   │  │ gamma_dollar    = Γ × S² × multiplier                  │
   │  │                   单位: $ / ($1 underlying move)²       │
   │  │                   注: per $1 的二阶导，不含额外系数     │
   │  │                                                         │
   │  │ vega_per_1pct   = Vega × multiplier                    │
   │  │                   单位: $ / 1% IV change                │
   │  │                   前提: Futu/Model 输出已是 per 1%      │
   │  │                                                         │
   │  │ theta_per_day   = Θ × multiplier                       │
   │  │                   单位: $ / day                         │
   │  │                   前提: 已归一化到 per-day              │
   │  │                                                         │
   │  │ 情景分析（Scenario Shock）单独计算：                    │
   │  │   shock_pnl_1pct = dollar_delta × S × 0.01             │
   │  │                  + 0.5 × gamma_dollar × (S × 0.01)²    │
   │  └─────────────────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ coverage（覆盖率指标）                                  │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ • valid_legs_count / total_legs_count                  │
   │  │ • valid_notional / total_notional                      │
   │  │ • missing_positions: list[position_id]                 │
   │  │                                                         │
   │  │ notional 定义（监控级精度，非清算级）：                  │
   │  │   notional = abs(qty) × underlying_spot × multiplier   │
   │  │   包含所有 legs（option + stock + cash）               │
   │  └─────────────────────────────────────────────────────────┘
   │
   └── 聚合维度：
       ├── 按 account_id → AccountGreeks
       └── 按 strategy_id → StrategyGreeks

5. Evaluate（阈值评估）
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ Coverage Check（优先级最高）                            │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ coverage < 95% → DATA_QUALITY CRIT                     │
   │  │ Dashboard 显示: "⚠️ Risk may be underestimated"         │
   │  │ (X legs / Y notional missing)                          │
   │  └─────────────────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ 阈值检查（WARN 80% / CRIT 100% / HARD 120%）           │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ • 方向: direction = ABS | MAX | MIN                    │
   │  │   - ABS: abs(value) <= limit（默认）                   │
   │  │   - MAX: value <= limit（上限）                        │
   │  │   - MIN: value >= limit（下限）                        │
   │  │ • 触发: value_eval >= threshold                        │
   │  │ • 回差解除: WARN 需回到 75% 才发 RECOVERED             │
   │  │            CRIT 需回到 90%                              │
   │  └─────────────────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ 变化率检测（Rate of Change）                            │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ 公式: abs(value_eval(t) - value_eval(t-5m))            │
   │  │       >= max(0.2 × limit, abs_step)                    │
   │  │                                                         │
   │  │ 注: 一律基于 value_eval（即 ABS 后的量）               │
   │  │ delta_change_signed 作为可选解释字段                   │
   │  └─────────────────────────────────────────────────────────┘
   │
   └── 输出: GreeksEvalResult（见 Section 2.3）

6. Alert（告警处理）
   ├── level-scoped dedupe（按级别不同冷却时间）
   │   ├── WARN: 900s (15分钟)
   │   ├── CRIT: 300s (5分钟)
   │   └── HARD: 60s (1分钟)
   ├── escalation-through（升级时穿透冷却，立即告警）
   ├── CRIT/HARD → 保存 Snapshot 到 GreeksSnapshotStore
   │              （含 Top N 贡献度 legs，按触发 metric 排序）
   ├── RECOVERED → 发送恢复通知
   └── DATA_QUALITY → 单独告警类型，不与 Greeks 阈值混淆

7. Publish
   │
   │  ┌─────────────────────────────────────────────────────────┐
   │  │ WebSocket 推送策略                                      │
   │  ├─────────────────────────────────────────────────────────┤
   │  │ • WS 只推增量 / 最新快照                                │
   │  │ • 断线重连流程：                                        │
   │  │   1. GET /api/greeks/snapshot → 获取最新完整状态        │
   │  │   2. Subscribe WS → 接收后续增量                        │
   │  │ • 历史查询走 GreeksSnapshotStore API                    │
   │  └─────────────────────────────────────────────────────────┘
   │
   └── 存储：
       ├── Redis pub/sub → Dashboard 实时推送
       └── GreeksSnapshotStore → 时序存储 + 快照
```

---

## 2. 数据模型设计

### 2.1 枚举定义

```python
# backend/src/greeks/models.py

from enum import Enum


class GreeksDataSource(str, Enum):
    """Greeks 数据来源"""
    FUTU = "futu"
    MODEL = "model"
    CACHED = "cached"


class GreeksModel(str, Enum):
    """Greeks 计算模型（当 source=MODEL 或 cached_from=MODEL 时使用）"""
    FUTU = "futu"              # Futu 提供的值（视为 model）
    BS = "bs"                  # Black-Scholes
    BJERKSUND = "bjerksund"    # Bjerksund-Stensland (美式)


class GreeksLevel(str, Enum):
    """告警级别"""
    NORMAL = "normal"
    WARN = "warn"
    CRIT = "crit"
    HARD = "hard"


class GreeksMetric(str, Enum):
    """Greeks 指标类型"""
    DELTA = "delta"
    GAMMA = "gamma"
    VEGA = "vega"
    THETA = "theta"
    COVERAGE = "coverage"
    IMPLIED_VOLATILITY = "iv"  # IV 异常监控（非 Greek 但复用告警引擎）


class ThresholdDirection(str, Enum):
    """阈值方向"""
    ABS = "abs"    # abs(value) <= limit
    MAX = "max"    # value <= limit（上限）
    MIN = "min"    # value >= limit（下限）
```

### 2.2 核心数据结构

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class PositionGreeks:
    """单个持仓的 Greeks（规范化后）

    数值类型规范：
    - 内部计算/存储统一用 Decimal
    - API/WS 输出时转 float（带 4 位小数 rounding）

    符号约定（dollar_delta）：
    - Long Call: 正
    - Long Put: 负
    - Short Call: 负
    - Short Put: 正

    Dollar Greeks 公式：
    - dollar_delta = Δ × S × multiplier
      单位: $ / $1 underlying move

    - gamma_dollar = Γ × S² × multiplier
      单位: $ / ($1 underlying move)²
      这是 per $1 的二阶导，不含额外系数

    - vega_per_1pct = Vega × multiplier
      单位: $ / 1% IV change

    - theta_per_day = Θ × multiplier
      单位: $ / day
    """

    position_id: int
    symbol: str                    # 期权 symbol（唯一标识）
    underlying_symbol: str

    # ========== 输入参数（用于审计/复算）==========
    quantity: int                  # 正=多头，负=空头
    multiplier: int                # 合约乘数（美股期权通常 100）
    underlying_price: Decimal      # 标的现价
    option_type: Literal["call", "put"]
    strike: Decimal
    expiry: str                    # ISO date string

    # ========== Dollar Greeks（Canonical，单一数值类型）==========
    dollar_delta: Decimal          # $ / $1 underlying move
    gamma_dollar: Decimal          # $ / ($1 underlying move)²
    vega_per_1pct: Decimal         # $ / 1% IV change
    theta_per_day: Decimal         # $ / day

    # ========== 数据来源 ==========
    source: GreeksDataSource
    model: GreeksModel | None      # source=MODEL 时必填
    cached_from_source: GreeksDataSource | None = None  # source=CACHED 时
    cached_from_model: GreeksModel | None = None

    # ========== 数据质量 ==========
    valid: bool = True
    quality_warnings: list[str] = field(default_factory=list)
    staleness_seconds: int = 0
    as_of_ts: datetime = field(default_factory=datetime.utcnow)

    # ========== 用于 coverage 计算 ==========
    notional: Decimal = Decimal("0")  # abs(qty) × underlying_price × multiplier


@dataclass
class AggregatedGreeks:
    """聚合后的组合 Greeks"""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    # Dollar Greeks 汇总
    dollar_delta: Decimal
    gamma_dollar: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal

    # Coverage 指标
    valid_legs_count: int
    total_legs_count: int
    valid_notional: Decimal
    total_notional: Decimal
    missing_positions: list[int] = field(default_factory=list)

    @property
    def coverage_pct(self) -> Decimal:
        if self.total_notional == 0:
            return Decimal("100.0")
        return (self.valid_notional / self.total_notional * 100).quantize(Decimal("0.01"))

    @property
    def is_coverage_sufficient(self) -> bool:
        return self.coverage_pct >= Decimal("95.0")

    # 元数据
    as_of_ts: datetime = field(default_factory=datetime.utcnow)
    calc_duration_ms: int = 0
```

### 2.3 评估结果模型

```python
@dataclass
class GreeksEvalResult:
    """单个指标的评估结果

    value_raw vs value_eval:
    - value_raw: 带符号的真实值（用于解释和 drill-down）
    - value_eval: 用于比较的值（direction=ABS 时为 abs）

    变化率检测一律基于 value_eval（即 ABS 后的量）
    """

    # 范围
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    # 指标
    metric: GreeksMetric

    # 评估结果
    level: GreeksLevel
    trigger_type: Literal["THRESHOLD", "RATE_OF_CHANGE", "COVERAGE"]

    # 数值（分离 raw 和 eval 避免歧义）
    value_raw: Decimal          # 带符号的真实值
    value_eval: Decimal         # 用于比较的值（ABS 时为 abs）
    limit: Decimal              # 配置的限额（永远正数）
    threshold: Decimal          # 触发的阈值（如 limit × 0.8）
    direction: ThresholdDirection  # 评估方向

    # 变化率相关（仅 RATE_OF_CHANGE 时有值）
    window_seconds: int | None = None
    delta_change: Decimal | None = None         # 基于 value_eval 的变化量
    delta_change_signed: Decimal | None = None  # 带符号变化（可选解释字段）

    # 动作
    should_alert: bool = False
    should_recover: bool = False

    # 去重键（用于 AlertDedupeStore）
    dedupe_key: str = ""  # "{scope}:{scope_id}:{metric}:{level}"

    # 可读解释
    explain: str = ""  # "abs(delta) 45000 >= 80% of limit 50000"

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.scope}:{self.scope_id}:{self.metric.value}:{self.level.value}"
```

### 2.4 配置模型

```python
@dataclass
class GreeksThresholdConfig:
    """单个 Greek 指标的阈值配置"""

    metric: GreeksMetric

    # 阈值方向
    direction: ThresholdDirection = ThresholdDirection.ABS  # 默认用绝对值

    # 绝对限额（永远正数）
    limit: Decimal = Decimal("0")

    # 百分比阈值
    warn_pct: Decimal = Decimal("0.80")   # 80%
    crit_pct: Decimal = Decimal("1.00")   # 100%
    hard_pct: Decimal = Decimal("1.20")   # 120%

    # 回差阈值（hysteresis）
    warn_recover_pct: Decimal = Decimal("0.75")  # 回到 75% 解除 WARN
    crit_recover_pct: Decimal = Decimal("0.90")  # 回到 90% 解除 CRIT

    # 变化率检测
    rate_window_seconds: int = 300  # 5 分钟
    rate_change_pct: Decimal = Decimal("0.20")   # 20% of limit
    rate_change_abs: Decimal = Decimal("0")      # 绝对变化阈值


@dataclass
class GreeksLimitsConfig:
    """Greeks 限额配置（账户或策略级别）"""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    thresholds: dict[GreeksMetric, GreeksThresholdConfig] = field(
        default_factory=dict
    )

    # Coverage 阈值
    min_coverage_pct: Decimal = Decimal("95.0")

    # 告警冷却（按级别不同）
    dedupe_window_seconds_by_level: dict[GreeksLevel, int] = field(
        default_factory=lambda: {
            GreeksLevel.WARN: 900,   # 15 分钟
            GreeksLevel.CRIT: 300,   # 5 分钟
            GreeksLevel.HARD: 60,    # 1 分钟
        }
    )

    @classmethod
    def default_account_config(cls, account_id: str) -> "GreeksLimitsConfig":
        """默认账户级配置"""
        return cls(
            scope="ACCOUNT",
            scope_id=account_id,
            thresholds={
                GreeksMetric.DELTA: GreeksThresholdConfig(
                    metric=GreeksMetric.DELTA,
                    direction=ThresholdDirection.ABS,  # abs(delta) <= limit
                    limit=Decimal("50000"),
                    rate_change_abs=Decimal("5000"),
                ),
                GreeksMetric.GAMMA: GreeksThresholdConfig(
                    metric=GreeksMetric.GAMMA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("10000"),
                    rate_change_abs=Decimal("1000"),
                ),
                GreeksMetric.VEGA: GreeksThresholdConfig(
                    metric=GreeksMetric.VEGA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("20000"),
                    rate_change_abs=Decimal("2000"),
                ),
                GreeksMetric.THETA: GreeksThresholdConfig(
                    metric=GreeksMetric.THETA,
                    direction=ThresholdDirection.ABS,  # abs(theta) <= limit
                    limit=Decimal("5000"),             # 正数限额
                    rate_change_abs=Decimal("500"),
                ),
                GreeksMetric.IMPLIED_VOLATILITY: GreeksThresholdConfig(
                    metric=GreeksMetric.IMPLIED_VOLATILITY,
                    direction=ThresholdDirection.MAX,  # IV <= limit
                    limit=Decimal("2.0"),              # 200% IV 上限
                    rate_change_abs=Decimal("0.3"),    # 30% IV 变化
                ),
            },
        )
```

### 2.5 快照存储模型

```python
@dataclass
class GreeksSnapshot:
    """Greeks 快照（存储形态：一行一个 scope）

    存储策略（方案 1）：
    - 同一个 snapshot_batch_id 产生多行：1 行 ACCOUNT + N 行 STRATEGY
    - position_details 存在单独的 greeks_snapshot_details 表
    - ALERT_TRIGGERED 时只存 Top N 贡献度 legs（按触发 metric 排序）

    保留策略：
    - PERIODIC: 保留 7 天（通过定时 job 清理）
    - ALERT_TRIGGERED: 保留 90 天（通过 Timescale retention）
    """

    id: str  # UUID，每行唯一
    snapshot_batch_id: str  # UUID，同一批次共享
    snapshot_type: Literal["PERIODIC", "ALERT_TRIGGERED", "MANUAL"]

    # 范围
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    # 聚合数据
    dollar_delta: Decimal
    gamma_dollar: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal

    # Coverage
    coverage_pct: Decimal
    valid_legs_count: int
    total_legs_count: int

    # 告警信息（如果是 ALERT_TRIGGERED）
    trigger_evals: list[GreeksEvalResult] = field(default_factory=list)

    # 元数据
    as_of_ts: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GreeksSnapshotDetailConfig:
    """快照明细配置"""
    top_n: int = 10  # 保存 Top N 贡献度 legs


@dataclass
class GreeksSnapshotDetail:
    """快照明细（单独表，仅告警时保存 Top N）

    ranking 按触发的 metric 排序：
    - 如果是 DELTA 超限，按 abs(dollar_delta) 排
    - 如果是 VEGA 超限，按 abs(vega_per_1pct) 排
    """

    snapshot_id: str  # FK to greeks_snapshots.id
    position_greeks: PositionGreeks
    rank_metric: GreeksMetric       # 排名使用的指标
    contribution_rank: int          # 排名（1 = 最大贡献）
    contribution_value: Decimal     # 贡献值（abs）
```

### 2.6 数据库表结构

```sql
-- 主表：快照（TimescaleDB hypertable）
CREATE TABLE greeks_snapshots (
    id UUID PRIMARY KEY,
    snapshot_batch_id UUID NOT NULL,  -- 同一批次
    snapshot_type VARCHAR(20) NOT NULL,
    scope VARCHAR(20) NOT NULL,
    scope_id VARCHAR(50) NOT NULL,

    -- Dollar Greeks
    dollar_delta NUMERIC(18, 4) NOT NULL,
    gamma_dollar NUMERIC(18, 4) NOT NULL,
    vega_per_1pct NUMERIC(18, 4) NOT NULL,
    theta_per_day NUMERIC(18, 4) NOT NULL,

    -- Coverage
    coverage_pct NUMERIC(5, 2) NOT NULL,
    valid_legs_count INT NOT NULL,
    total_legs_count INT NOT NULL,

    -- 告警信息（JSONB，仅 ALERT_TRIGGERED）
    trigger_evals JSONB,  -- list[GreeksEvalResult]

    -- 时间
    as_of_ts TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('greeks_snapshots', 'as_of_ts');

CREATE INDEX idx_greeks_snapshots_scope
    ON greeks_snapshots(scope, scope_id, as_of_ts DESC);
CREATE INDEX idx_greeks_snapshots_batch
    ON greeks_snapshots(snapshot_batch_id);
CREATE INDEX idx_greeks_snapshots_alert
    ON greeks_snapshots(snapshot_type, as_of_ts DESC)
    WHERE snapshot_type = 'ALERT_TRIGGERED';


-- 明细表：持仓 Greeks（仅告警时存 Top N）
CREATE TABLE greeks_snapshot_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES greeks_snapshots(id) ON DELETE CASCADE,
    rank_metric VARCHAR(20) NOT NULL,
    contribution_rank INT NOT NULL,
    contribution_value NUMERIC(18, 4) NOT NULL,
    position_data JSONB NOT NULL,  -- PositionGreeks 序列化
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_greeks_details_snapshot
    ON greeks_snapshot_details(snapshot_id);


-- 保留策略
-- 1. ALERT_TRIGGERED: Timescale retention 90 天
SELECT add_retention_policy('greeks_snapshots', INTERVAL '90 days');

-- 2. PERIODIC: 定时 job 清理 7 天前的数据
-- 实现方式：APScheduler job 或 pg_cron
-- DELETE FROM greeks_snapshots
-- WHERE snapshot_type = 'PERIODIC' AND as_of_ts < NOW() - INTERVAL '7 days';
```

### 2.7 IV 缓存模型

```python
@dataclass
class IVCacheEntry:
    """IV 缓存条目

    Redis Key: iv_cache:{option_symbol}
    - option_symbol 是期权唯一标识（含 underlying/strike/expiry/type）
    - 例如: AAPL240119C00150000
    """

    option_symbol: str
    underlying_symbol: str

    # 核心数据
    implied_volatility: Decimal  # 0.0 ~ 2.0+（允许高 IV）
    underlying_price: Decimal

    # 利率与分红（V1 先简化，预留字段）
    risk_free_rate: Decimal = Decimal("0.05")  # 年化
    dividend_yield: Decimal | None = None       # 预留，V1 不使用

    # 元数据
    source: GreeksDataSource = GreeksDataSource.FUTU
    as_of_ts: datetime = field(default_factory=datetime.utcnow)
    ttl_seconds: int = 300  # 5 分钟 TTL

    @property
    def expires_at(self) -> datetime:
        from datetime import timedelta
        return self.as_of_ts + timedelta(seconds=self.ttl_seconds)

    @property
    def is_stale(self) -> bool:
        return datetime.utcnow() > self.expires_at
```

**Redis 存储结构：**

```
Key: iv_cache:{option_symbol}
Value: JSON(IVCacheEntry)
TTL: 300 seconds

Key: iv_underlying:{underlying_symbol}
Value: JSON({
  price: Decimal,
  risk_free_rate: Decimal,
  dividend_yield: Decimal | null,
  as_of_ts: datetime
})
TTL: 60 seconds
```

---

## 3. 核心组件实现

（待续）

---

## 4. API 设计

（待续）

---

## 5. 前端架构

（待续）

---

## 6. 实施计划

（待续）

---

## 附录 A：关键决策记录

### A.1 为什么用 Decimal 而非 float？

**原因**：
1. 金融计算需要精确的小数表示，避免浮点误差累积
2. 与数据库 NUMERIC 类型直接对应
3. API 输出时统一转 float（带 rounding）

### A.2 为什么 Theta limit 用正数 + ABS 方向？

**原因**：
1. 负数 limit 会导致百分比阈值逻辑混乱
2. 统一用 abs(value) <= limit 简化评估逻辑
3. UI 展示时可保留符号，但评估用 abs

### A.3 为什么 value 分成 value_raw 和 value_eval？

**原因**：
1. value_raw 用于解释和 drill-down（保留符号信息）
2. value_eval 用于阈值比较（direction=ABS 时为 abs）
3. 避免 UI/日志对不齐的问题

### A.4 为什么告警冷却按级别区分？

**原因**：
1. HARD 级别需要快速响应，冷却时间应短（60s）
2. WARN 级别相对不紧急，冷却时间可长（15min）
3. 避免"要么告警风暴，要么漏报紧急情况"的两难

### A.5 为什么快照明细按触发 metric 排序？

**原因**：
1. 如果是 Vega 超限，排名应按 Vega 贡献度
2. 便于事后分析"为什么这个 metric 超了"
3. Top N 贡献度才有意义
