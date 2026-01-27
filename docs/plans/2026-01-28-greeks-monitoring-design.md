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

### 3.1 模块结构

```
backend/src/greeks/
├── __init__.py
├── models.py           # 数据模型（Section 2 定义）
├── calculator.py       # GreeksCalculator（单持仓计算）
├── aggregator.py       # GreeksAggregator（组合聚合）
├── alert_engine.py     # GreeksAlertEngine（告警评估）
├── monitor.py          # GreeksMonitor（主调度器）
├── iv_cache.py         # IVCacheManager（IV 缓存）
├── snapshot_store.py   # GreeksSnapshotStore（时序存储）
└── config.py           # 配置加载
```

### 3.2 GreeksCalculator

```python
# backend/src/greeks/calculator.py

import logging
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal

from src.greeks.models import (
    GreeksDataSource,
    GreeksModel,
    PositionGreeks,
)
from src.greeks.iv_cache import IVCacheManager
from src.models.position import Position

logger = logging.getLogger(__name__)


class GreeksCalculator:
    """单持仓 Greeks 计算器

    职责：
    1. 优先使用 Futu API 获取 Greeks
    2. Fallback 到模型计算（BS / Bjerksund-Stensland）
    3. 输出规范化的 PositionGreeks

    设计原则：
    - 不可变：所有方法返回新对象，不修改输入
    - 单一职责：只做单持仓计算，不做聚合
    - 显式依赖：IVCacheManager 通过构造函数注入
    """

    # 配置常量
    MAX_STALENESS_SECONDS = 300  # 超过此秒数视为过时
    DEFAULT_MULTIPLIER = 100     # 美股期权默认乘数

    def __init__(
        self,
        iv_cache: IVCacheManager,
        futu_client: "FutuGreeksClient | None" = None,
    ):
        self._iv_cache = iv_cache
        self._futu_client = futu_client

    async def calculate(self, position: Position) -> PositionGreeks:
        """计算单个持仓的 Greeks

        流程：
        1. 尝试 Futu API
        2. 失败则 fallback 到模型计算
        3. 规范化单位
        4. 质量检查
        """
        # 获取基础数据
        underlying_price = await self._get_underlying_price(position.symbol)
        multiplier = self._get_multiplier(position)
        option_type = self._normalize_option_type(position.put_call)
        is_american = self._determine_is_american(position)

        # 构建基础 PositionGreeks（用于 invalid_from 场景）
        base_greeks = PositionGreeks(
            position_id=position.id,
            symbol=position.symbol,
            underlying_symbol=self._extract_underlying(position.symbol),
            quantity=position.quantity,
            multiplier=multiplier,
            underlying_price=underlying_price,
            option_type=option_type,
            strike=position.strike or Decimal("0"),
            expiry=position.expiry.isoformat() if position.expiry else "",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            source=GreeksDataSource.FUTU,
            model=None,
            valid=False,
            quality_warnings=["Not yet calculated"],
            notional=abs(position.quantity) * underlying_price * multiplier,
        )

        # Step 1: 尝试 Futu API
        greeks = await self._try_futu_greeks(base_greeks, position)

        # Step 2: Fallback 到模型计算
        if greeks is None or not greeks.valid:
            greeks = await self._calculate_model_greeks(
                base_greeks, position, underlying_price, is_american
            )

        # Step 3: 规范化单位（确保符合 canonical convention）
        greeks = self._normalize_units(greeks, underlying_price, multiplier)

        # Step 4: 质量检查（软检查，标记 warning 而非剔除）
        greeks = self._validate_greeks(greeks)

        return greeks

    async def _try_futu_greeks(
        self, base: PositionGreeks, position: Position
    ) -> PositionGreeks | None:
        """尝试从 Futu API 获取 Greeks"""
        if self._futu_client is None:
            return None

        try:
            raw = await self._futu_client.get_greeks(position.symbol)
            if raw is None:
                return None

            now = datetime.now(timezone.utc)
            staleness = int((now - raw.as_of_ts).total_seconds())

            # 检查数据新鲜度（单一来源）
            if staleness > self.MAX_STALENESS_SECONDS:
                logger.warning(
                    f"Futu Greeks stale: {position.symbol}, staleness={staleness}s"
                )
                return None

            return replace(
                base,
                dollar_delta=raw.delta,
                gamma_dollar=raw.gamma,
                vega_per_1pct=raw.vega,
                theta_per_day=raw.theta,
                source=GreeksDataSource.FUTU,
                model=GreeksModel.FUTU,
                valid=True,
                quality_warnings=[],
                staleness_seconds=staleness,
                as_of_ts=raw.as_of_ts,
            )
        except Exception as e:
            logger.warning(f"Futu Greeks failed: {position.symbol}, error={e}")
            return None

    async def _calculate_model_greeks(
        self,
        base: PositionGreeks,
        position: Position,
        underlying_price: Decimal,
        is_american: bool,
    ) -> PositionGreeks:
        """使用模型计算 Greeks"""
        # 从缓存获取 IV
        iv_entry = await self._iv_cache.get(position.symbol)
        if iv_entry is None or iv_entry.is_stale:
            return replace(
                base,
                valid=False,
                quality_warnings=["IV not available for model calculation"],
            )

        # 计算到期时间（更精确：考虑市场收盘时间）
        time_to_expiry = self._calc_time_to_expiry(position.expiry)
        if time_to_expiry <= 0:
            return replace(
                base,
                valid=False,
                quality_warnings=["Option expired"],
            )

        # 选择模型
        model = GreeksModel.BJERKSUND if is_american else GreeksModel.BS

        try:
            if is_american:
                raw_greeks = self._bjerksund_greeks(
                    S=float(underlying_price),
                    K=float(position.strike),
                    T=time_to_expiry,
                    r=float(iv_entry.risk_free_rate),
                    sigma=float(iv_entry.implied_volatility),
                    option_type=base.option_type,
                )
            else:
                raw_greeks = self._bs_greeks(
                    S=float(underlying_price),
                    K=float(position.strike),
                    T=time_to_expiry,
                    r=float(iv_entry.risk_free_rate),
                    sigma=float(iv_entry.implied_volatility),
                    option_type=base.option_type,
                )

            return replace(
                base,
                dollar_delta=Decimal(str(raw_greeks["delta"])),
                gamma_dollar=Decimal(str(raw_greeks["gamma"])),
                vega_per_1pct=Decimal(str(raw_greeks["vega"])),
                theta_per_day=Decimal(str(raw_greeks["theta"])),
                source=GreeksDataSource.MODEL,
                model=model,
                valid=True,
                quality_warnings=[],
                staleness_seconds=int(
                    (datetime.now(timezone.utc) - iv_entry.as_of_ts).total_seconds()
                ),
                as_of_ts=iv_entry.as_of_ts,
            )
        except Exception as e:
            logger.error(f"Model calculation failed: {position.symbol}, error={e}")
            return replace(
                base,
                valid=False,
                quality_warnings=[f"Model calculation failed: {e}"],
            )

    def _normalize_units(
        self,
        greeks: PositionGreeks,
        underlying_price: Decimal,
        multiplier: int,
    ) -> PositionGreeks:
        """规范化为 Dollar Greeks

        输入假设：
        - delta: per-share delta（-1 到 1）
        - gamma: per-share gamma
        - vega: per 1% IV change（已经是 per 1%）
        - theta: per-day theta

        输出（带 qty 符号）：
        - dollar_delta = Δ × S × multiplier × qty
        - gamma_dollar = Γ × S² × multiplier × qty
        - vega_per_1pct = Vega × multiplier × qty
        - theta_per_day = Θ × multiplier × qty
        """
        qty = greeks.quantity
        S = underlying_price

        return replace(
            greeks,
            dollar_delta=greeks.dollar_delta * S * multiplier * qty,
            gamma_dollar=greeks.gamma_dollar * S * S * multiplier * qty,
            vega_per_1pct=greeks.vega_per_1pct * multiplier * qty,
            theta_per_day=greeks.theta_per_day * multiplier * qty,
        )

    def _validate_greeks(self, greeks: PositionGreeks) -> PositionGreeks:
        """质量检查（软检查）

        原则：
        - NaN/Inf → valid=false（无法使用）
        - 异常值 → valid=true + quality_warnings（可用但需注意）
        """
        warnings = list(greeks.quality_warnings)
        valid = greeks.valid

        # NaN/Inf 检测（使用 Decimal 方法）
        for field_name in ["dollar_delta", "gamma_dollar", "vega_per_1pct", "theta_per_day"]:
            val = getattr(greeks, field_name)
            if self._is_invalid_decimal(val):
                valid = False
                warnings.append(f"{field_name} is NaN or Inf")

        # Delta 范围检查（宽松，允许 deep ITM 美式超过 1）
        implied_delta = self._calc_implied_delta(greeks)
        if implied_delta is not None and abs(implied_delta) > Decimal("1.2"):
            warnings.append(f"implied_delta={implied_delta} outside [-1.2, 1.2]")

        # Theta 符号检查（软检查 - 美式/空头可能有正 theta）
        # 不再标记为异常，仅做日志记录

        return replace(greeks, valid=valid, quality_warnings=warnings)

    def _calc_implied_delta(self, greeks: PositionGreeks) -> Decimal | None:
        """从 dollar_delta 反推 per-share delta"""
        if greeks.quantity == 0 or greeks.underlying_price == 0:
            return None
        return greeks.dollar_delta / (
            greeks.underlying_price * greeks.multiplier * greeks.quantity
        )

    @staticmethod
    def _is_invalid_decimal(val: Decimal) -> bool:
        """检查 Decimal 是否为 NaN 或 Inf"""
        try:
            return val.is_nan() or val.is_infinite()
        except (InvalidOperation, AttributeError):
            return True

    @staticmethod
    def _normalize_option_type(put_call) -> Literal["call", "put"]:
        """规范化期权类型为小写"""
        if put_call is None:
            return "call"
        val = str(put_call).lower()
        return "put" if val in ("put", "p") else "call"

    def _determine_is_american(self, position: Position) -> bool:
        """判断是否为美式期权

        规则：
        - 美股期权默认为美式
        - 可通过 position 元数据覆盖
        """
        # V1: 美股期权默认美式
        # TODO: 从 position 元数据读取
        return True

    def _calc_time_to_expiry(self, expiry_date) -> float:
        """计算到期时间（年化）

        精度：考虑市场收盘时间（16:00 ET）
        """
        if expiry_date is None:
            return 0.0

        from datetime import date, time
        import pytz

        et_tz = pytz.timezone("US/Eastern")
        now_et = datetime.now(et_tz)

        # 到期日 16:00 ET
        expiry_dt = datetime.combine(
            expiry_date if isinstance(expiry_date, date) else date.fromisoformat(str(expiry_date)),
            time(16, 0),
            tzinfo=et_tz,
        )

        delta = expiry_dt - now_et
        days = delta.total_seconds() / 86400
        return max(days / 365.0, 0.0)

    def _get_multiplier(self, position: Position) -> int:
        """获取合约乘数"""
        # TODO: 从 position 元数据或产品数据读取
        return self.DEFAULT_MULTIPLIER

    async def _get_underlying_price(self, symbol: str) -> Decimal:
        """获取标的现价"""
        underlying = self._extract_underlying(symbol)
        entry = await self._iv_cache.get_underlying(underlying)
        if entry:
            return entry.price
        # Fallback: 从 Futu 获取
        if self._futu_client:
            price = await self._futu_client.get_price(underlying)
            if price:
                return Decimal(str(price))
        return Decimal("100")  # 最后 fallback

    @staticmethod
    def _extract_underlying(option_symbol: str) -> str:
        """从期权 symbol 提取标的 symbol"""
        # 简单实现：取字母部分
        import re
        match = re.match(r"^([A-Z]+)", option_symbol)
        return match.group(1) if match else option_symbol

    # ========== 模型计算（简化版，实际应用更复杂）==========

    def _bs_greeks(
        self, S: float, K: float, T: float, r: float, sigma: float, option_type: str
    ) -> dict:
        """Black-Scholes Greeks 计算"""
        import math
        from scipy.stats import norm

        if T <= 0 or sigma <= 0:
            return {"delta": 0, "gamma": 0, "vega": 0, "theta": 0}

        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "call":
            delta = norm.cdf(d1)
            theta = (
                -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                - r * K * math.exp(-r * T) * norm.cdf(d2)
            ) / 365
        else:
            delta = norm.cdf(d1) - 1
            theta = (
                -S * norm.pdf(d1) * sigma / (2 * math.sqrt(T))
                + r * K * math.exp(-r * T) * norm.cdf(-d2)
            ) / 365

        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T) / 100  # per 1% IV

        return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}

    def _bjerksund_greeks(
        self, S: float, K: float, T: float, r: float, sigma: float, option_type: str
    ) -> dict:
        """Bjerksund-Stensland 美式期权 Greeks（简化版）

        完整实现应使用数值方法计算 Greeks
        V1 先用 BS 近似 + 早期行权调整
        """
        # V1: 使用 BS 近似
        bs_greeks = self._bs_greeks(S, K, T, r, sigma, option_type)

        # 美式期权调整（简化）
        # 真正的实现需要用有限差分或解析近似
        return bs_greeks

    # ========== 静态工厂方法 ==========

    @staticmethod
    def invalid_from(
        position: Position,
        reason: str,
        underlying_price: Decimal = Decimal("0"),
    ) -> PositionGreeks:
        """创建无效的 PositionGreeks（用于错误情况）"""
        multiplier = 100  # 默认
        return PositionGreeks(
            position_id=position.id,
            symbol=position.symbol,
            underlying_symbol=position.symbol[:4],  # 简化提取
            quantity=position.quantity,
            multiplier=multiplier,
            underlying_price=underlying_price,
            option_type="call",
            strike=position.strike or Decimal("0"),
            expiry=position.expiry.isoformat() if position.expiry else "",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            source=GreeksDataSource.MODEL,
            model=None,
            valid=False,
            quality_warnings=[reason],
            notional=abs(position.quantity) * underlying_price * multiplier,
        )
```

### 3.3 GreeksAggregator

```python
# backend/src/greeks/aggregator.py

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from src.greeks.models import (
    AggregatedGreeks,
    GreeksMetric,
    PositionGreeks,
)

logger = logging.getLogger(__name__)


@dataclass
class _Accumulator:
    """聚合累加器（内部使用）

    设计原则：
    - 单遍 O(N) 聚合
    - 同时计算 computed_greeks 和 coverage
    """

    # Dollar Greeks 累加
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage 统计
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")
    missing_positions: list[int] = field(default_factory=list)
    warning_positions: list[int] = field(default_factory=list)

    # 时间戳追踪
    as_of_ts_min: datetime | None = None
    as_of_ts_max: datetime | None = None

    def add(self, pg: PositionGreeks) -> None:
        """累加单个持仓"""
        self.total_legs_count += 1
        self.total_notional += pg.notional

        # 更新时间戳范围
        if self.as_of_ts_min is None or pg.as_of_ts < self.as_of_ts_min:
            self.as_of_ts_min = pg.as_of_ts
        if self.as_of_ts_max is None or pg.as_of_ts > self.as_of_ts_max:
            self.as_of_ts_max = pg.as_of_ts

        if pg.valid:
            self.valid_legs_count += 1
            self.valid_notional += pg.notional
            self.dollar_delta += pg.dollar_delta
            self.gamma_dollar += pg.gamma_dollar
            self.vega_per_1pct += pg.vega_per_1pct
            self.theta_per_day += pg.theta_per_day

            # 有警告但仍有效的持仓
            if pg.quality_warnings:
                self.warning_positions.append(pg.position_id)
        else:
            self.missing_positions.append(pg.position_id)


class GreeksAggregator:
    """组合 Greeks 聚合器

    职责：
    1. 聚合多个 PositionGreeks 到账户/策略级别
    2. 计算 coverage 指标
    3. 提供 Top N 贡献度排名

    设计原则：
    - 单遍 O(N) 聚合
    - 输出两套数据：computed_greeks + coverage
    - as_of_ts 取最小值（最保守/最旧）
    """

    def aggregate(
        self,
        positions: list[PositionGreeks],
        scope: Literal["ACCOUNT", "STRATEGY"],
        scope_id: str,
    ) -> AggregatedGreeks:
        """聚合持仓列表

        Args:
            positions: PositionGreeks 列表
            scope: 聚合范围
            scope_id: 范围 ID

        Returns:
            AggregatedGreeks 包含聚合结果和 coverage
        """
        acc = _Accumulator()

        # 单遍聚合
        for pg in positions:
            acc.add(pg)

        # 处理空持仓情况
        has_positions = acc.total_legs_count > 0
        as_of_ts = acc.as_of_ts_min or datetime.now(timezone.utc)

        return AggregatedGreeks(
            scope=scope,
            scope_id=scope_id,
            strategy_id=scope_id if scope == "STRATEGY" else None,
            dollar_delta=acc.dollar_delta,
            gamma_dollar=acc.gamma_dollar,
            vega_per_1pct=acc.vega_per_1pct,
            theta_per_day=acc.theta_per_day,
            valid_legs_count=acc.valid_legs_count,
            total_legs_count=acc.total_legs_count,
            valid_notional=acc.valid_notional,
            total_notional=acc.total_notional,
            missing_positions=acc.missing_positions,
            warning_legs_count=len(acc.warning_positions),
            has_positions=has_positions,
            as_of_ts=as_of_ts,
            as_of_ts_min=acc.as_of_ts_min,
            as_of_ts_max=acc.as_of_ts_max,
        )

    def aggregate_by_strategy(
        self,
        positions: list[PositionGreeks],
        account_id: str,
    ) -> tuple[AggregatedGreeks, dict[str, AggregatedGreeks]]:
        """按策略聚合，同时计算账户级汇总

        Returns:
            (account_greeks, {strategy_id: strategy_greeks})
        """
        # 按 strategy_id 分组
        by_strategy: dict[str, list[PositionGreeks]] = {}
        for pg in positions:
            strategy_id = pg.strategy_id or "_unassigned_"
            if strategy_id not in by_strategy:
                by_strategy[strategy_id] = []
            by_strategy[strategy_id].append(pg)

        # 策略级聚合
        strategy_greeks = {
            sid: self.aggregate(pgs, "STRATEGY", sid)
            for sid, pgs in by_strategy.items()
        }

        # 账户级聚合
        account_greeks = self.aggregate(positions, "ACCOUNT", account_id)

        return account_greeks, strategy_greeks

    def get_top_contributors(
        self,
        positions: list[PositionGreeks],
        metric: GreeksMetric,
        top_n: int = 10,
    ) -> list[tuple[PositionGreeks, Decimal]]:
        """获取指定指标的 Top N 贡献者

        Args:
            positions: PositionGreeks 列表
            metric: 排序指标（不支持 COVERAGE/IV）
            top_n: 返回数量

        Returns:
            [(PositionGreeks, contribution_value)] 按贡献度降序
        """
        # COVERAGE 和 IV 不适用于持仓贡献度排名
        if metric in (GreeksMetric.COVERAGE, GreeksMetric.IMPLIED_VOLATILITY):
            logger.warning(f"get_top_contributors: metric {metric} not supported")
            return []

        # 字段映射
        field_map = {
            GreeksMetric.DELTA: "dollar_delta",
            GreeksMetric.GAMMA: "gamma_dollar",
            GreeksMetric.VEGA: "vega_per_1pct",
            GreeksMetric.THETA: "theta_per_day",
        }

        field_name = field_map.get(metric)
        if not field_name:
            return []

        # 计算贡献度并排序
        contributions = [
            (pg, abs(getattr(pg, field_name)))
            for pg in positions
            if pg.valid
        ]
        contributions.sort(key=lambda x: x[1], reverse=True)

        return contributions[:top_n]
```

需要更新 `AggregatedGreeks` 模型以支持新字段：

```python
# 在 models.py 中更新 AggregatedGreeks

@dataclass
class AggregatedGreeks:
    """聚合后的组合 Greeks"""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    strategy_id: str | None = None  # 仅 STRATEGY scope 时有值

    # Dollar Greeks 汇总
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage 指标
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")
    missing_positions: list[int] = field(default_factory=list)
    warning_legs_count: int = 0
    has_positions: bool = True

    # 时间戳
    as_of_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    as_of_ts_min: datetime | None = None  # 最早数据时间（最保守）
    as_of_ts_max: datetime | None = None  # 最新数据时间

    # 元数据
    calc_duration_ms: int = 0

    @property
    def coverage_pct(self) -> Decimal:
        if not self.has_positions:
            return Decimal("100.0")
        if self.total_notional == 0:
            return Decimal("100.0")
        return (self.valid_notional / self.total_notional * 100).quantize(Decimal("0.01"))

    @property
    def is_coverage_sufficient(self) -> bool:
        return self.coverage_pct >= Decimal("95.0")

    @property
    def staleness_seconds(self) -> int:
        """最大过时时间（基于最早数据）"""
        if self.as_of_ts_min is None:
            return 0
        delta = datetime.now(timezone.utc) - self.as_of_ts_min
        return int(delta.total_seconds())
```

### 3.4 GreeksAlertEngine

```python
# backend/src/greeks/alert_engine.py

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from src.greeks.models import (
    AggregatedGreeks,
    GreeksEvalResult,
    GreeksLevel,
    GreeksLimitsConfig,
    GreeksMetric,
    GreeksThresholdConfig,
    ThresholdDirection,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertState:
    """告警状态（用于状态机）"""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    metric: GreeksMetric
    current_level: GreeksLevel = GreeksLevel.NORMAL
    last_alert_ts: dict[GreeksLevel, datetime] = field(default_factory=dict)
    last_value_eval: Decimal | None = None  # 用于 ROC 检测


class GreeksAlertEngine:
    """Greeks 告警评估引擎

    职责：
    1. 阈值触发检测（WARN/CRIT/HARD）
    2. 变化率异常检测
    3. 告警去重（level-scoped）
    4. 升级穿透（escalation-through）
    5. 回差恢复检测（hysteresis）

    状态管理：
    - AlertState 存储在内存（单进程）
    - 可选持久化到 Redis（多进程）
    """

    def __init__(self, limits_config: GreeksLimitsConfig):
        self._config = limits_config
        self._states: dict[str, AlertState] = {}  # key: "{scope}:{scope_id}:{metric}"

    def evaluate(
        self,
        greeks: AggregatedGreeks,
        prev_greeks: AggregatedGreeks | None = None,
    ) -> list[GreeksEvalResult]:
        """评估聚合 Greeks 并生成告警

        Args:
            greeks: 当前聚合结果
            prev_greeks: 上一次聚合结果（用于 ROC 检测）

        Returns:
            触发的告警列表（已去重）
        """
        results: list[GreeksEvalResult] = []

        # 1. Coverage 检查（优先）
        coverage_result = self._evaluate_coverage(greeks)
        if coverage_result:
            results.append(coverage_result)

        # 2. 各 metric 阈值检查
        for metric, threshold_cfg in self._config.thresholds.items():
            if metric == GreeksMetric.COVERAGE:
                continue  # 已单独处理

            result = self._evaluate_metric(greeks, metric, threshold_cfg, prev_greeks)
            if result:
                results.append(result)

        # 3. 合并告警（同一 metric 可能有 THRESHOLD + ROC）
        merged = self._merge_alerts(results)

        return merged

    def _evaluate_coverage(self, greeks: AggregatedGreeks) -> GreeksEvalResult | None:
        """评估 Coverage"""
        coverage_pct = greeks.coverage_pct
        min_coverage = self._config.min_coverage_pct

        state_key = f"{greeks.scope}:{greeks.scope_id}:coverage"
        state = self._get_or_create_state(
            state_key, greeks.scope, greeks.scope_id, GreeksMetric.COVERAGE
        )

        # Coverage 低于阈值
        if coverage_pct < min_coverage:
            new_level = GreeksLevel.CRIT  # Coverage 问题直接 CRIT

            should_alert = self._should_alert(state, new_level)
            if should_alert:
                state.current_level = new_level
                state.last_alert_ts[new_level] = datetime.now(timezone.utc)

            return GreeksEvalResult(
                scope=greeks.scope,
                scope_id=greeks.scope_id,
                metric=GreeksMetric.COVERAGE,
                level=new_level,
                trigger_types={"COVERAGE"},
                value_raw=coverage_pct,
                value_eval=coverage_pct,
                limit=min_coverage,
                threshold=min_coverage,
                direction=ThresholdDirection.MIN,
                should_alert=should_alert,
                should_recover=False,
                explains=[
                    f"coverage {coverage_pct}% < {min_coverage}% "
                    f"({greeks.valid_legs_count}/{greeks.total_legs_count} legs valid)"
                ],
            )

        # Coverage 恢复
        if state.current_level != GreeksLevel.NORMAL:
            state.current_level = GreeksLevel.NORMAL
            return GreeksEvalResult(
                scope=greeks.scope,
                scope_id=greeks.scope_id,
                metric=GreeksMetric.COVERAGE,
                level=GreeksLevel.NORMAL,
                trigger_types={"COVERAGE"},
                value_raw=coverage_pct,
                value_eval=coverage_pct,
                limit=min_coverage,
                threshold=min_coverage,
                direction=ThresholdDirection.MIN,
                should_alert=False,
                should_recover=True,
                explains=[f"coverage recovered to {coverage_pct}%"],
            )

        return None

    def _evaluate_metric(
        self,
        greeks: AggregatedGreeks,
        metric: GreeksMetric,
        cfg: GreeksThresholdConfig,
        prev_greeks: AggregatedGreeks | None,
    ) -> GreeksEvalResult | None:
        """评估单个 metric"""
        # 获取原始值
        value_raw = self._get_metric_value(greeks, metric)
        value_eval = self._apply_direction(value_raw, cfg.direction)
        limit = cfg.limit

        state_key = f"{greeks.scope}:{greeks.scope_id}:{metric.value}"
        state = self._get_or_create_state(
            state_key, greeks.scope, greeks.scope_id, metric
        )

        # 计算触发级别
        trigger_types: set[str] = set()
        explains: list[str] = []
        new_level = GreeksLevel.NORMAL
        threshold_triggered = Decimal("0")

        # 阈值检查
        if self._is_breached(value_eval, limit * cfg.hard_pct, cfg.direction):
            new_level = GreeksLevel.HARD
            threshold_triggered = limit * cfg.hard_pct
            trigger_types.add("THRESHOLD")
            explains.append(
                f"{self._direction_explain(cfg.direction, value_raw)} {value_eval} >= "
                f"{cfg.hard_pct*100:.0f}% of limit {limit}"
            )
        elif self._is_breached(value_eval, limit * cfg.crit_pct, cfg.direction):
            new_level = GreeksLevel.CRIT
            threshold_triggered = limit * cfg.crit_pct
            trigger_types.add("THRESHOLD")
            explains.append(
                f"{self._direction_explain(cfg.direction, value_raw)} {value_eval} >= "
                f"{cfg.crit_pct*100:.0f}% of limit {limit}"
            )
        elif self._is_breached(value_eval, limit * cfg.warn_pct, cfg.direction):
            new_level = GreeksLevel.WARN
            threshold_triggered = limit * cfg.warn_pct
            trigger_types.add("THRESHOLD")
            explains.append(
                f"{self._direction_explain(cfg.direction, value_raw)} {value_eval} >= "
                f"{cfg.warn_pct*100:.0f}% of limit {limit}"
            )

        # 变化率检测
        roc_triggered = self._check_rate_of_change(
            state, value_eval, cfg, prev_greeks, metric
        )
        if roc_triggered:
            delta_change = abs(value_eval - (state.last_value_eval or Decimal("0")))
            trigger_types.add("RATE_OF_CHANGE")
            explains.append(
                f"rate of change {delta_change} >= "
                f"max({cfg.rate_change_pct*100:.0f}% of {limit}, {cfg.rate_change_abs})"
            )
            # ROC 至少触发 WARN
            if new_level == GreeksLevel.NORMAL:
                new_level = GreeksLevel.WARN
                threshold_triggered = Decimal("0")  # ROC-only 没有阈值

        # 更新 ROC 检测用的历史值
        state.last_value_eval = value_eval

        # 恢复检测（带回差）
        if new_level == GreeksLevel.NORMAL and state.current_level != GreeksLevel.NORMAL:
            should_recover = self._is_recovered(
                value_eval, limit, cfg, state.current_level
            )
            if should_recover:
                old_level = state.current_level
                state.current_level = GreeksLevel.NORMAL
                return GreeksEvalResult(
                    scope=greeks.scope,
                    scope_id=greeks.scope_id,
                    metric=metric,
                    level=GreeksLevel.NORMAL,
                    trigger_types={"RECOVERED"},
                    value_raw=value_raw,
                    value_eval=value_eval,
                    limit=limit,
                    threshold=threshold_triggered,
                    direction=cfg.direction,
                    should_alert=False,
                    should_recover=True,
                    explains=[f"recovered from {old_level.value} to NORMAL"],
                )
            else:
                # 未达到回差阈值，保持当前级别
                return None

        # 降级检测（HARD→CRIT, CRIT→WARN 也需要回差）
        if (
            new_level != GreeksLevel.NORMAL
            and state.current_level != GreeksLevel.NORMAL
            and self._level_value(new_level) < self._level_value(state.current_level)
        ):
            # 检查是否满足降级的回差条件
            if not self._can_downgrade(value_eval, limit, cfg, state.current_level, new_level):
                # 保持高级别，不降级
                return None

        # 无触发
        if not trigger_types:
            return None

        # 去重判断
        should_alert = self._should_alert(state, new_level)
        if should_alert:
            state.current_level = new_level
            state.last_alert_ts[new_level] = datetime.now(timezone.utc)

        return GreeksEvalResult(
            scope=greeks.scope,
            scope_id=greeks.scope_id,
            metric=metric,
            level=new_level,
            trigger_types=trigger_types,
            value_raw=value_raw,
            value_eval=value_eval,
            limit=limit,
            threshold=threshold_triggered,
            direction=cfg.direction,
            should_alert=should_alert,
            should_recover=False,
            explains=explains,
        )

    def _is_breached(
        self, value_eval: Decimal, threshold: Decimal, direction: ThresholdDirection
    ) -> bool:
        """判断是否超过阈值

        Args:
            value_eval: 用于比较的值（ABS 方向已取绝对值）
            threshold: 阈值（永远正数）
            direction: 阈值方向
        """
        if direction == ThresholdDirection.ABS:
            # value_eval 已经是 abs，直接比较
            return value_eval >= threshold
        elif direction == ThresholdDirection.MAX:
            # 上限：value <= threshold 为 OK，value > threshold 为 breach
            return value_eval > threshold
        elif direction == ThresholdDirection.MIN:
            # 下限：value >= threshold 为 OK，value < threshold 为 breach
            return value_eval < threshold
        return False

    def _is_recovered(
        self,
        value_eval: Decimal,
        limit: Decimal,
        cfg: GreeksThresholdConfig,
        current_level: GreeksLevel,
    ) -> bool:
        """判断是否恢复（带回差）

        回差逻辑：
        - WARN 恢复需回到 75% (warn_recover_pct)
        - CRIT 恢复需回到 90% (crit_recover_pct)
        - HARD 恢复需回到 100% (crit_pct)
        """
        if current_level == GreeksLevel.WARN:
            recover_threshold = limit * cfg.warn_recover_pct
        elif current_level == GreeksLevel.CRIT:
            recover_threshold = limit * cfg.crit_recover_pct
        elif current_level == GreeksLevel.HARD:
            recover_threshold = limit * cfg.crit_pct  # HARD 恢复到 CRIT 以下
        else:
            return True

        # 恢复判断（与 breach 相反）
        if cfg.direction == ThresholdDirection.ABS:
            return value_eval < recover_threshold
        elif cfg.direction == ThresholdDirection.MAX:
            return value_eval <= recover_threshold
        elif cfg.direction == ThresholdDirection.MIN:
            return value_eval >= recover_threshold
        return True

    def _can_downgrade(
        self,
        value_eval: Decimal,
        limit: Decimal,
        cfg: GreeksThresholdConfig,
        from_level: GreeksLevel,
        to_level: GreeksLevel,
    ) -> bool:
        """判断是否可以降级（需要满足回差）"""
        # HARD → CRIT: 需要低于 CRIT 的回差阈值
        # CRIT → WARN: 需要低于 WARN 的回差阈值
        if from_level == GreeksLevel.HARD and to_level == GreeksLevel.CRIT:
            recover_threshold = limit * cfg.crit_recover_pct
        elif from_level == GreeksLevel.CRIT and to_level == GreeksLevel.WARN:
            recover_threshold = limit * cfg.warn_recover_pct
        else:
            return True

        if cfg.direction == ThresholdDirection.ABS:
            return value_eval < recover_threshold
        elif cfg.direction == ThresholdDirection.MAX:
            return value_eval <= recover_threshold
        elif cfg.direction == ThresholdDirection.MIN:
            return value_eval >= recover_threshold
        return True

    def _should_alert(self, state: AlertState, new_level: GreeksLevel) -> bool:
        """判断是否应该发送告警

        去重逻辑：
        1. 升级（escalation-through）：立即告警
        2. 同级别：检查冷却时间
        3. 降级：不告警（等待 RECOVERED）
        """
        if new_level == GreeksLevel.NORMAL:
            return False

        old_level = state.current_level

        # 升级：立即告警
        if self._level_value(new_level) > self._level_value(old_level):
            return True

        # 降级：不告警
        if self._level_value(new_level) < self._level_value(old_level):
            return False

        # 同级别：检查冷却
        last_ts = state.last_alert_ts.get(new_level)
        if last_ts is None:
            return True

        cooldown = self._config.dedupe_window_seconds_by_level.get(new_level, 300)
        elapsed = (datetime.now(timezone.utc) - last_ts).total_seconds()
        return elapsed >= cooldown

    def _check_rate_of_change(
        self,
        state: AlertState,
        value_eval: Decimal,
        cfg: GreeksThresholdConfig,
        prev_greeks: AggregatedGreeks | None,
        metric: GreeksMetric,
    ) -> bool:
        """检测变化率异常"""
        if state.last_value_eval is None:
            return False

        delta = abs(value_eval - state.last_value_eval)
        threshold = max(
            cfg.limit * cfg.rate_change_pct,
            cfg.rate_change_abs,
        )

        return delta >= threshold

    @staticmethod
    def _apply_direction(value: Decimal, direction: ThresholdDirection) -> Decimal:
        """应用方向得到用于比较的值"""
        if direction == ThresholdDirection.ABS:
            return abs(value)
        return value

    @staticmethod
    def _direction_explain(direction: ThresholdDirection, value: Decimal) -> str:
        """生成方向说明"""
        if direction == ThresholdDirection.ABS:
            return f"abs({value})"
        return str(value)

    @staticmethod
    def _level_value(level: GreeksLevel) -> int:
        """级别数值化用于比较"""
        return {
            GreeksLevel.NORMAL: 0,
            GreeksLevel.WARN: 1,
            GreeksLevel.CRIT: 2,
            GreeksLevel.HARD: 3,
        }.get(level, 0)

    @staticmethod
    def _get_metric_value(greeks: AggregatedGreeks, metric: GreeksMetric) -> Decimal:
        """从聚合结果获取 metric 值"""
        mapping = {
            GreeksMetric.DELTA: greeks.dollar_delta,
            GreeksMetric.GAMMA: greeks.gamma_dollar,
            GreeksMetric.VEGA: greeks.vega_per_1pct,
            GreeksMetric.THETA: greeks.theta_per_day,
        }
        return mapping.get(metric, Decimal("0"))

    def _get_or_create_state(
        self,
        key: str,
        scope: Literal["ACCOUNT", "STRATEGY"],
        scope_id: str,
        metric: GreeksMetric,
    ) -> AlertState:
        """获取或创建告警状态"""
        if key not in self._states:
            self._states[key] = AlertState(
                scope=scope, scope_id=scope_id, metric=metric
            )
        return self._states[key]

    def _merge_alerts(self, results: list[GreeksEvalResult]) -> list[GreeksEvalResult]:
        """合并同一 metric 的多个触发类型"""
        merged: dict[str, GreeksEvalResult] = {}

        for r in results:
            key = f"{r.scope}:{r.scope_id}:{r.metric.value}"
            if key not in merged:
                merged[key] = r
            else:
                existing = merged[key]
                # 合并 trigger_types 和 explains
                merged[key] = GreeksEvalResult(
                    scope=r.scope,
                    scope_id=r.scope_id,
                    metric=r.metric,
                    level=max(existing.level, r.level, key=self._level_value),
                    trigger_types=existing.trigger_types | r.trigger_types,
                    value_raw=r.value_raw,
                    value_eval=r.value_eval,
                    limit=r.limit,
                    threshold=r.threshold if r.threshold else existing.threshold,
                    direction=r.direction,
                    should_alert=existing.should_alert or r.should_alert,
                    should_recover=existing.should_recover or r.should_recover,
                    explains=existing.explains + r.explains,
                )

        return list(merged.values())
```

需要更新 `GreeksEvalResult` 模型：

```python
# 在 models.py 中更新

@dataclass
class GreeksEvalResult:
    """单个指标的评估结果"""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    metric: GreeksMetric
    level: GreeksLevel

    # 触发类型（可能同时有多个）
    trigger_types: set[str] = field(default_factory=set)  # {"THRESHOLD", "RATE_OF_CHANGE", "COVERAGE", "RECOVERED"}

    # 数值
    value_raw: Decimal = Decimal("0")
    value_eval: Decimal = Decimal("0")
    limit: Decimal = Decimal("0")
    threshold: Decimal = Decimal("0")
    direction: ThresholdDirection = ThresholdDirection.ABS

    # 变化率相关
    window_seconds: int | None = None
    delta_change: Decimal | None = None
    delta_change_signed: Decimal | None = None

    # 动作
    should_alert: bool = False
    should_recover: bool = False

    # 去重键
    dedupe_key: str = ""

    # 可读解释（列表形式）
    explains: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.scope}:{self.scope_id}:{self.metric.value}:{self.level.value}"
```

### 3.5 GreeksMonitor

```python
# backend/src/greeks/monitor.py

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
import uuid

from src.greeks.aggregator import GreeksAggregator
from src.greeks.alert_engine import GreeksAlertEngine
from src.greeks.calculator import GreeksCalculator
from src.greeks.models import (
    AggregatedGreeks,
    GreeksEvalResult,
    GreeksLevel,
    GreeksLimitsConfig,
    PositionGreeks,
)
from src.greeks.snapshot_store import GreeksSnapshotStore

logger = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    """Monitor 配置"""

    account_id: str
    poll_interval_seconds: int = 30
    min_refresh_interval_seconds: float = 1.0  # 最小刷新间隔（节流）
    enable_aligned_scheduling: bool = True  # 对齐到整数秒


class GreeksMonitor:
    """Greeks 监控主调度器

    职责：
    1. 事件驱动刷新（Position CRUD / Order Fill）
    2. 定时轮询（backstop）
    3. 告警发送（通过回调）
    4. 快照存储

    设计原则：
    - Single-flight：并发刷新请求合并为一次
    - 优雅停止：running 检查 + pending 取消
    - 节流：防止过于频繁刷新
    - 对齐调度：poll_loop 对齐到整数秒
    """

    def __init__(
        self,
        config: MonitorConfig,
        limits_config: GreeksLimitsConfig,
        calculator: GreeksCalculator,
        aggregator: GreeksAggregator,
        alert_engine: GreeksAlertEngine,
        snapshot_store: GreeksSnapshotStore,
        position_fetcher: Callable,  # async () -> list[Position]
        alert_sender: Callable[[GreeksEvalResult], None],  # 告警发送回调
        redis_publisher: Callable[[str, dict], None] | None = None,
    ):
        self._config = config
        self._limits_config = limits_config
        self._calculator = calculator
        self._aggregator = aggregator
        self._alert_engine = alert_engine
        self._snapshot_store = snapshot_store
        self._position_fetcher = position_fetcher
        self._alert_sender = alert_sender
        self._redis_publisher = redis_publisher

        # 状态
        self._running = False
        self._poll_task: asyncio.Task | None = None

        # Single-flight 机制
        self._refresh_lock = asyncio.Lock()
        self._pending_refresh = False
        self._dirty = False

        # 节流（使用 monotonic clock）
        self._last_refresh_mono: float = 0.0

        # 缓存
        self._last_greeks: AggregatedGreeks | None = None
        self._last_strategy_greeks: dict[str, AggregatedGreeks] = {}

        # 发送端去重缓存
        self._sent_alerts: dict[str, float] = {}  # dedupe_key -> sent_mono_time

        # Metrics
        self._refresh_count = 0
        self._positions_total = 0

    async def start(self) -> None:
        """启动监控"""
        if self._running:
            logger.warning("GreeksMonitor already running")
            return

        self._running = True
        logger.info(f"Starting GreeksMonitor for account {self._config.account_id}")

        # 首次刷新
        await self.refresh()

        # 启动 poll loop
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """停止监控"""
        if not self._running:
            return

        self._running = False
        logger.info("Stopping GreeksMonitor...")

        # 取消 poll task
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # 等待进行中的刷新完成
        async with self._refresh_lock:
            pass

        logger.info("GreeksMonitor stopped")

    def mark_dirty(self) -> None:
        """标记需要刷新（事件驱动调用）"""
        self._dirty = True

    async def refresh(self) -> AggregatedGreeks | None:
        """刷新 Greeks（Single-flight + 节流）

        并发调用会合并为一次刷新。
        """
        if not self._running:
            logger.debug("refresh() called but monitor not running")
            return None

        # 节流检查
        now_mono = time.monotonic()
        elapsed = now_mono - self._last_refresh_mono
        if elapsed < self._config.min_refresh_interval_seconds:
            logger.debug(f"refresh() throttled, elapsed={elapsed:.2f}s")
            return self._last_greeks

        # Single-flight：如果已有刷新在进行，标记 pending
        if self._refresh_lock.locked():
            self._pending_refresh = True
            return self._last_greeks

        async with self._refresh_lock:
            # Running 检查
            if not self._running:
                return None

            return await self._do_refresh()

    async def _do_refresh(self) -> AggregatedGreeks | None:
        """执行实际刷新"""
        run_id = str(uuid.uuid4())[:8]
        start_time = time.monotonic()

        try:
            # 1. 获取持仓
            positions = await self._position_fetcher()
            self._positions_total = len(positions)

            if not positions:
                logger.debug(f"[{run_id}] No positions to monitor")
                self._dirty = False
                return None

            # 2. 计算每个持仓的 Greeks
            position_greeks: list[PositionGreeks] = []
            for pos in positions:
                if not self._running:
                    return None
                try:
                    pg = await self._calculator.calculate(pos)
                    # 添加 strategy_id
                    pg.strategy_id = pos.strategy_id
                    position_greeks.append(pg)
                except Exception as e:
                    logger.error(f"[{run_id}] Calculator error for {pos.id}: {e}")
                    pg = GreeksCalculator.invalid_from(pos, str(e))
                    pg.strategy_id = pos.strategy_id
                    position_greeks.append(pg)

            # 3. 聚合
            account_greeks, strategy_greeks = self._aggregator.aggregate_by_strategy(
                position_greeks, self._config.account_id
            )
            account_greeks.calc_duration_ms = int((time.monotonic() - start_time) * 1000)

            # 4. 告警评估
            results = self._alert_engine.evaluate(account_greeks, self._last_greeks)

            # 策略级别告警
            for sid, sg in strategy_greeks.items():
                prev_sg = self._last_strategy_greeks.get(sid)
                strategy_results = self._alert_engine.evaluate(sg, prev_sg)
                results.extend(strategy_results)

            # 5. 发送告警（带发送端去重）
            for result in results:
                if result.should_alert or result.should_recover:
                    self._send_alert_dedupe(result)

            # 6. 保存快照（CRIT/HARD 时）
            critical_results = [
                r for r in results
                if r.level in (GreeksLevel.CRIT, GreeksLevel.HARD) and r.should_alert
            ]
            if critical_results:
                await self._save_snapshot(
                    account_greeks, strategy_greeks, position_greeks, critical_results
                )

            # 7. 发布到 Redis
            if self._redis_publisher:
                self._publish_to_redis(account_greeks, strategy_greeks, run_id)

            # 更新缓存
            self._last_greeks = account_greeks
            self._last_strategy_greeks = strategy_greeks
            self._last_refresh_mono = time.monotonic()
            self._refresh_count += 1
            self._dirty = False

            logger.debug(
                f"[{run_id}] Refresh complete: "
                f"{len(position_greeks)} positions, "
                f"{len(results)} alerts, "
                f"{account_greeks.calc_duration_ms}ms"
            )

            # 处理 pending refresh
            if self._pending_refresh:
                self._pending_refresh = False
                # 不递归，让下次 refresh() 调用处理

            return account_greeks

        except Exception as e:
            logger.exception(f"[{run_id}] Refresh failed: {e}")
            return None

    async def _poll_loop(self) -> None:
        """定时轮询循环"""
        interval = self._config.poll_interval_seconds

        while self._running:
            try:
                # 对齐调度：计算到下一个整数倍时间点的等待时间
                if self._config.enable_aligned_scheduling:
                    now = time.time()
                    next_tick = ((now // interval) + 1) * interval
                    wait_time = next_tick - now
                else:
                    wait_time = interval

                await asyncio.sleep(wait_time)

                if not self._running:
                    break

                # 检查是否需要刷新
                if self._dirty or True:  # backstop 总是刷新
                    await self.refresh()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Poll loop error: {e}")
                await asyncio.sleep(1)  # 错误后短暂等待

    def _send_alert_dedupe(self, result: GreeksEvalResult) -> None:
        """发送告警（带发送端去重）"""
        now_mono = time.monotonic()

        # 检查发送端缓存
        last_sent = self._sent_alerts.get(result.dedupe_key)
        if last_sent:
            cooldown = self._limits_config.dedupe_window_seconds_by_level.get(
                result.level, 300
            )
            if now_mono - last_sent < cooldown:
                logger.debug(f"Alert dedupe: {result.dedupe_key} in cooldown")
                return

        # 发送
        try:
            self._alert_sender(result)
            self._sent_alerts[result.dedupe_key] = now_mono
            logger.info(
                f"Alert sent: {result.metric.value} {result.level.value} "
                f"for {result.scope}:{result.scope_id}"
            )
        except Exception as e:
            logger.error(f"Alert send failed: {e}")

        # 清理过期缓存（防止内存泄漏）
        self._cleanup_sent_cache(now_mono)

    def _cleanup_sent_cache(self, now_mono: float) -> None:
        """清理过期的发送缓存"""
        max_cooldown = max(
            self._limits_config.dedupe_window_seconds_by_level.values()
        )
        cutoff = now_mono - max_cooldown * 2

        expired = [k for k, v in self._sent_alerts.items() if v < cutoff]
        for k in expired:
            del self._sent_alerts[k]

    async def _save_snapshot(
        self,
        account_greeks: AggregatedGreeks,
        strategy_greeks: dict[str, AggregatedGreeks],
        position_greeks: list[PositionGreeks],
        trigger_results: list[GreeksEvalResult],
    ) -> None:
        """保存快照"""
        try:
            await self._snapshot_store.save_alert_snapshot(
                account_greeks=account_greeks,
                strategy_greeks=strategy_greeks,
                position_greeks=position_greeks,
                trigger_results=trigger_results,
            )
        except Exception as e:
            logger.error(f"Snapshot save failed: {e}")

    def _publish_to_redis(
        self,
        account_greeks: AggregatedGreeks,
        strategy_greeks: dict[str, AggregatedGreeks],
        run_id: str,
    ) -> None:
        """发布到 Redis"""
        if not self._redis_publisher:
            return

        channel = f"greeks:{self._config.account_id}"
        payload = {
            "run_id": run_id,
            "account_id": self._config.account_id,
            "account": {
                "dollar_delta": float(account_greeks.dollar_delta),
                "gamma_dollar": float(account_greeks.gamma_dollar),
                "vega_per_1pct": float(account_greeks.vega_per_1pct),
                "theta_per_day": float(account_greeks.theta_per_day),
                "coverage_pct": float(account_greeks.coverage_pct),
                "valid_legs_count": account_greeks.valid_legs_count,
                "total_legs_count": account_greeks.total_legs_count,
                "as_of_ts_min": account_greeks.as_of_ts_min.isoformat()
                if account_greeks.as_of_ts_min else None,
                "as_of_ts_max": account_greeks.as_of_ts_max.isoformat()
                if account_greeks.as_of_ts_max else None,
                "staleness_seconds": account_greeks.staleness_seconds,
            },
            "strategies": {
                sid: {
                    "dollar_delta": float(sg.dollar_delta),
                    "gamma_dollar": float(sg.gamma_dollar),
                    "vega_per_1pct": float(sg.vega_per_1pct),
                    "theta_per_day": float(sg.theta_per_day),
                    "coverage_pct": float(sg.coverage_pct),
                }
                for sid, sg in strategy_greeks.items()
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            self._redis_publisher(channel, payload)
        except Exception as e:
            logger.error(f"Redis publish failed: {e}")

    # ========== Metrics 接口 ==========

    def get_metrics(self) -> dict:
        """获取监控指标"""
        return {
            "running": self._running,
            "refresh_count": self._refresh_count,
            "positions_total": self._positions_total,
            "last_refresh_ago_seconds": time.monotonic() - self._last_refresh_mono
            if self._last_refresh_mono else None,
            "dirty": self._dirty,
            "pending_refresh": self._pending_refresh,
        }
```

---

## 4. API 设计

### 4.1 API 端点概览

```
/api/greeks/
├── GET  /snapshot                    # 获取当前 Greeks 快照（账户+策略列表）
├── GET  /snapshot/{strategy_id}      # 获取单个策略 Greeks（返回 strategy 单对象）
├── GET  /limits                      # 获取当前限额配置
├── PUT  /limits                      # 更新限额配置（V2）
├── GET  /history                     # 历史 Greeks 查询
├── GET  /alerts                      # 告警历史查询
├── GET  /contributors/{metric}       # Top N 贡献者查询
├── WS   /ws                          # WebSocket 实时推送
```

**认证**：所有端点需要 `Authorization: Bearer {token}`，从 token 解析 `account_id`。

**Meta 规范（所有接口统一）**：
```python
"meta": {
    "as_of_ts": "...",           # 展示用主时间 = as_of_ts_max
    "as_of_ts_min": "...",       # 数据覆盖范围最早时间
    "as_of_ts_max": "...",       # 数据覆盖范围最晚时间
    "staleness_seconds": 5,      # = now - as_of_ts_max
    "request_id": "req_abc123"
}
```

**通用错误码**：
| HTTP | Code | 说明 |
|------|------|------|
| 400 | INVALID_ARGUMENT | 参数错误（metric 枚举无效、top_n>50 等） |
| 401 | UNAUTHORIZED | 未认证或 token 无效 |
| 403 | FORBIDDEN | token 有效但无该 account 权限 |
| 429 | RATE_LIMITED | 请求过于频繁（尤其 WS/历史查询） |
| 500 | INTERNAL_ERROR | 服务器内部错误 |
| 503 | GREEKS_NOT_AVAILABLE | Greeks 服务不可用 |

**错误响应格式**：
```python
{
    "error": {
        "code": "INVALID_ARGUMENT",
        "message": "metric must be one of: delta, gamma, vega, theta",
        "details": {
            "field": "metric",
            "value": "invalid_metric"
        }
    },
    "meta": {
        "request_id": "req_abc123"  # 错误响应也带 request_id
    }
}
```

### 4.2 核心端点设计

#### GET /api/greeks/snapshot

获取当前 Greeks 快照，包含账户级汇总 + 所有策略明细。

**Query Parameters:**
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| include_strategies | bool | N | true | 是否包含策略列表 |
| include_warnings | bool | N | false | 是否包含 quality_warnings |

**Response 200:**
```python
{
    "data": {
        "account": {
            "account_id": "acc123",
            "dollar_delta": 45000.0,
            "gamma_dollar": 8500.0,
            "vega_per_1pct": 15000.0,
            "theta_per_day": -3200.0,
            "coverage_pct": 98.5,
            "valid_legs_count": 12,
            "total_legs_count": 12,
            "warning_legs_count": 1,
            "levels": {
                "delta": "warn",
                "gamma": "normal",
                "vega": "normal",
                "theta": "normal",
                "coverage": "normal"
            },
            "utilization": {
                "delta": { "value": 45000.0, "limit": 50000.0, "pct": 90.0 },
                "gamma": { "value": 8500.0, "limit": 10000.0, "pct": 85.0 },
                "vega": { "value": 15000.0, "limit": 20000.0, "pct": 75.0 },
                "theta": { "value": 3200.0, "limit": 5000.0, "pct": 64.0 }
            }
        },
        "strategies": [
            {
                "strategy_id": "wheel_aapl",
                "dollar_delta": 25000.0,
                "gamma_dollar": 5000.0,
                "vega_per_1pct": 8000.0,
                "theta_per_day": -1800.0,
                "coverage_pct": 100.0,
                "valid_legs_count": 5,
                "total_legs_count": 5,
                "levels": { "delta": "normal", "gamma": "normal", ... }
            },
            ...
        ]
    },
    "meta": {
        "as_of_ts": "2026-01-28T10:30:00Z",
        "as_of_ts_min": "2026-01-28T10:29:55Z",
        "as_of_ts_max": "2026-01-28T10:30:00Z",
        "staleness_seconds": 5,
        "calc_duration_ms": 120,
        "request_id": "req_abc123"
    }
}
```

**Response 503 (服务不可用):**

Headers:
```
Retry-After: 1
Cache-Control: no-store
```

Body:
```python
{
    "error": {
        "code": "GREEKS_NOT_AVAILABLE",
        "message": "Greeks calculation in progress",
        "details": {
            "reason": "starting",  # starting | in_progress | downstream_unavailable
            "downstream_service": null,
            "retry_after_ms": 1000
        }
    },
    "meta": {
        "request_id": "req_abc123"
    }
}
```

#### GET /api/greeks/snapshot/{strategy_id}

获取单个策略的 Greeks 快照。

**Response 200:**
```python
{
    "data": {
        "strategy": {
            "strategy_id": "wheel_aapl",
            "dollar_delta": 25000.0,
            "gamma_dollar": 5000.0,
            "vega_per_1pct": 8000.0,
            "theta_per_day": -1800.0,
            "coverage_pct": 100.0,
            "valid_legs_count": 5,
            "total_legs_count": 5,
            "warning_legs_count": 0,
            "levels": { ... },
            "utilization": { ... }
        }
    },
    "meta": { ... }
}
```

**Response 404:**
```python
{
    "error": {
        "code": "STRATEGY_NOT_FOUND",
        "message": "Strategy 'invalid_id' not found or has no positions"
    },
    "meta": { "request_id": "..." }
}
```

#### GET /api/greeks/contributors/{metric}

获取指定 metric 的 Top N 贡献者持仓。

**Path Parameters:**
| 参数 | 类型 | 说明 |
|------|------|------|
| metric | enum | delta / gamma / vega / theta |

**Query Parameters:**
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| top_n | int | N | 10 | 返回数量，最大 50 |
| strategy_id | string | N | - | 筛选特定策略 |

**Response 200:**
```python
{
    "data": {
        "metric": "delta",
        "total_value": 45000.0,
        "total_abs_value": 63000.0,
        "contributors": [
            {
                "rank": 1,
                "position_id": 123,
                "symbol": "AAPL260220C00180000",
                "underlying": "AAPL",
                "strategy_id": "wheel_aapl",
                "quantity": 10,
                "option_type": "call",
                "strike": 180.0,
                "expiry": "2026-02-20",
                "value_signed": 18000.0,
                "contribution_abs": 18000.0,
                "contribution_pct": 28.57
            },
            ...
        ]
    },
    "meta": {
        "as_of_ts": "2026-01-28T10:30:00Z",
        "as_of_ts_min": "2026-01-28T10:29:55Z",
        "as_of_ts_max": "2026-01-28T10:30:00Z",
        "staleness_seconds": 5,
        "request_id": "req_abc123"
    }
}
```

#### GET /api/greeks/history

历史 Greeks 查询（时序数据）。

**Query Parameters:**
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| scope | enum | N | ACCOUNT | ACCOUNT / STRATEGY |
| scope_id | string | 条件 | - | scope=STRATEGY 时必填 |
| start_ts | datetime | Y | - | 开始时间（ISO 8601） |
| end_ts | datetime | N | now | 结束时间 |
| interval | enum | N | 5m | 1m / 5m / 15m / 1h / raw |
| metrics | list | N | 全部 | 指标列表 |

**interval 限制：**
- `raw`：最大时间跨度 24h，超过返回 400
- `1m`：最大时间跨度 7d
- `5m/15m`：最大时间跨度 30d
- `1h`：最大时间跨度 90d

**Response 200:**
```python
{
    "data": {
        "scope": "ACCOUNT",
        "scope_id": "acc123",
        "interval": "5m",
        "points": [
            {
                "ts": "2026-01-28T10:00:00Z",
                "dollar_delta": 42000.0,
                "gamma_dollar": 8000.0,
                "vega_per_1pct": 14000.0,
                "theta_per_day": -3000.0,
                "coverage_pct": 100.0
            },
            ...
        ]
    },
    "meta": {
        "as_of_ts": "2026-01-28T10:30:00Z",
        "as_of_ts_min": "2026-01-28T10:00:00Z",
        "as_of_ts_max": "2026-01-28T10:30:00Z",
        "staleness_seconds": 0,
        "total_points": 7,
        "request_id": "req_abc123"
    }
}
```

### 4.3 WebSocket 协议

#### 4.3.1 连接与认证

**Endpoint:** `wss://api.example.com/api/greeks/ws`

**认证方式：**

| 方式 | 适用场景 | 安全性 |
|------|----------|--------|
| **首条消息 auth（推荐）** | 生产环境 | ✅ token 不进 URL/日志 |
| Query param | 仅开发/调试 | ⚠️ 需短期或一次性 token |

```python
# 方式 1（推荐）：首条消息认证
ws.connect("wss://api.example.com/api/greeks/ws")
ws.send({ "type": "auth", "token": "{jwt_token}" })

# 方式 2（仅开发调试）：Query parameter
wss://api.example.com/api/greeks/ws?token={short_lived_token}
# ⚠️ 生产环境必须：网关脱敏 query string，禁止记录到日志
```

**连接流程：**
```
Client                                 Server
   |                                      |
   |------- WS Connect ------------------>|
   |------- { type: "auth" } ------------>|
   |                                      | 验证 token
   |<------ { type: "connected" } --------|
   |                                      |
   |------- { type: "subscribe" } ------->|
   |<------ { type: "subscribed" } -------|
   |                                      |
   |<------ { type: "snapshot" } ---------|  首次全量
   |<------ { type: "update" } -----------|  后续增量（patch）
   |<------ { type: "alert" } ------------|  告警推送
   |                                      |
   |<------ { type: "ping" } -------------|  30s 心跳
   |------- { type: "pong" } ------------>|
   |                                      |
```

#### 4.3.2 消息类型定义

**通用 Meta 结构（所有服务端消息必带）：**
```python
"meta": {
    "connection_id": "conn_abc123",
    "seq": 12,
    "server_ts": "2026-01-28T10:30:00Z"
}
```

**服务端消息类型：**

| 类型 | 说明 |
|------|------|
| connected | 连接成功 |
| subscribed | 订阅确认 |
| snapshot | 全量快照 |
| update | 增量更新（Patch 语义） |
| alert | 告警推送 |
| ping | 心跳（30s 间隔） |
| error | 错误通知 |

**Update 合并规则（Patch 语义）：**

| 字段 | 合并语义 |
|------|----------|
| `account` | Deep-merge patch：未出现的字段保持不变 |
| `account.levels` | 按 key merge：`{ delta: "crit" }` 只更新 delta |
| `account.utilization` | 按 key merge |
| `strategies` | 以 `strategy_id` 为 key 做 patch |
| `strategies[i]` | Deep-merge：未出现字段保持不变 |
| `strategies[i].deleted=true` | Tombstone：从本地状态删除该策略 |

**客户端消息类型：**

| 类型 | 说明 |
|------|------|
| auth | 认证（首条消息） |
| subscribe | 订阅频道 |
| unsubscribe | 取消订阅 |
| pong | 心跳响应 |

**subscribe 选项：**
```python
{
    "type": "subscribe",
    "channels": ["greeks", "alerts"],
    "options": {
        "include_strategies": true,
        "strategy_ids": ["wheel_aapl", "cc_tsla"],  # null = 全部
        "metrics": ["delta", "gamma"],              # null = 全部
        "throttle_ms": 1000
    }
}
```

#### 4.3.3 序列号与断线重连

**seq 机制用途：**
- 检测增量缺失（服务端丢弃消息）
- 识别重连导致的不连续
- 发现实现 bug（乱序写入）

**关键规则：**
1. 每个 `connection_id` 的 seq 从 0 开始单调递增
2. `connection_id` 变化 → 新连接，seq 重新从 0 开始
3. 同一 `connection_id` 出现 seq gap → 增量丢失，需要重新请求 snapshot

**断线重连流程：**
1. 检测断线（WS close / ping timeout 90s）
2. 指数退避重连：1s → 2s → 4s → 8s → 16s（最大）
3. 重连成功后：收到新 connection_id，发送 subscribe，等待 snapshot 全量覆盖

#### 4.3.4 心跳机制

- 服务端每 **30s** 发送 `ping`
- 客户端需在 **90s 内** 回复 `pong`（考虑浏览器后台 tab throttling）
- 超时未收到 pong → 服务端关闭连接（code 4001）

#### 4.3.5 限流与背压

**服务端限流：**
| 限制项 | 值 | 说明 |
|--------|-----|------|
| 最大连接数/账户 | 5 | 超过发送 error 后关闭 |
| 最小推送间隔 | 100ms | 服务端硬限制 |
| 客户端节流 | 可配置 | subscribe.options.throttle_ms |
| 消息队列深度 | 100 | 超过触发 resync |

**队列溢出处理：**
发生溢出后，服务端直接发送一次 snapshot（seq 继续递增），客户端收到 snapshot 全量覆盖本地状态。

#### 4.3.6 连接关闭码

| Code | 名称 | 说明 | 关闭前发 error |
|------|------|------|----------------|
| 1000 | NORMAL | 正常关闭 | 否 |
| 1008 | AUTH_FAILED | 认证失败 | 是 |
| 1013 | SERVICE_OVERLOAD | 服务过载 | 是 |
| 4001 | HEARTBEAT_TIMEOUT | 90s 无 pong | 否 |
| 4002 | INVALID_SUBSCRIPTION | 订阅无效 | 是 |
| 4003 | TOO_MANY_CONNECTIONS | 连接数超限（>5） | 是 |

### 4.4 Pydantic Schema 定义

#### 4.4.1 基础类型与枚举

```python
# backend/src/greeks/schemas.py

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class GreeksMetricEnum(str, Enum):
    DELTA = "delta"
    GAMMA = "gamma"
    VEGA = "vega"
    THETA = "theta"
    COVERAGE = "coverage"


class GreeksLevelEnum(str, Enum):
    NORMAL = "normal"
    WARN = "warn"
    CRIT = "crit"
    HARD = "hard"


class GreeksScopeEnum(str, Enum):
    ACCOUNT = "ACCOUNT"
    STRATEGY = "STRATEGY"


class IntervalEnum(str, Enum):
    RAW = "raw"
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    ONE_HOUR = "1h"


class ThresholdDirectionEnum(str, Enum):
    ABS = "abs"
    MAX = "max"
    MIN = "min"


WSChannelType = Literal["greeks", "alerts"]
```

#### 4.4.2 通用响应结构

```python
class MetaResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    as_of_ts: datetime
    as_of_ts_min: datetime | None = None
    as_of_ts_max: datetime | None = None
    staleness_seconds: int = Field(..., ge=0)
    request_id: str
    calc_duration_ms: int | None = Field(None, ge=0)
    total_points: int | None = Field(None, ge=0)


class ErrorDetail(BaseModel):
    field: str | None = None
    value: str | None = None
    max_range_hours: int | None = None
    requested_range_hours: int | None = None
    reason: str | None = None
    downstream_service: str | None = None
    retry_after_ms: int | None = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: ErrorDetail | None = None


class APIErrorResponse(BaseModel):
    error: ErrorResponse
    meta: MetaResponse | None = None
```

#### 4.4.3 Snapshot Schema

```python
class UtilizationItem(BaseModel):
    value: float
    limit: float
    pct: float = Field(..., ge=0)


# Full 版本（REST Snapshot）
class LevelsMap(BaseModel):
    delta: GreeksLevelEnum = GreeksLevelEnum.NORMAL
    gamma: GreeksLevelEnum = GreeksLevelEnum.NORMAL
    vega: GreeksLevelEnum = GreeksLevelEnum.NORMAL
    theta: GreeksLevelEnum = GreeksLevelEnum.NORMAL
    coverage: GreeksLevelEnum = GreeksLevelEnum.NORMAL


class UtilizationMap(BaseModel):
    delta: UtilizationItem | None = None
    gamma: UtilizationItem | None = None
    vega: UtilizationItem | None = None
    theta: UtilizationItem | None = None


# Patch 版本（WS Update）
class LevelsPatch(BaseModel):
    delta: GreeksLevelEnum | None = None
    gamma: GreeksLevelEnum | None = None
    vega: GreeksLevelEnum | None = None
    theta: GreeksLevelEnum | None = None
    coverage: GreeksLevelEnum | None = None


class UtilizationPatch(BaseModel):
    delta: UtilizationItem | None = None
    gamma: UtilizationItem | None = None
    vega: UtilizationItem | None = None
    theta: UtilizationItem | None = None


class AccountGreeksResponse(BaseModel):
    account_id: str
    dollar_delta: float
    gamma_dollar: float
    vega_per_1pct: float
    theta_per_day: float
    coverage_pct: float = Field(..., ge=0, le=100)
    valid_legs_count: int = Field(..., ge=0)
    total_legs_count: int = Field(..., ge=0)
    warning_legs_count: int = Field(0, ge=0)
    levels: LevelsMap
    utilization: UtilizationMap


class StrategyGreeksResponse(BaseModel):
    strategy_id: str
    dollar_delta: float
    gamma_dollar: float
    vega_per_1pct: float
    theta_per_day: float
    coverage_pct: float = Field(..., ge=0, le=100)
    valid_legs_count: int = Field(..., ge=0)
    total_legs_count: int = Field(..., ge=0)
    warning_legs_count: int = Field(0, ge=0)
    levels: LevelsMap
    utilization: UtilizationMap | None = None


class SnapshotData(BaseModel):
    account: AccountGreeksResponse
    strategies: list[StrategyGreeksResponse] = Field(default_factory=list)


class SnapshotResponse(BaseModel):
    data: SnapshotData
    meta: MetaResponse


class SingleStrategyData(BaseModel):
    strategy: StrategyGreeksResponse


class SingleStrategyResponse(BaseModel):
    data: SingleStrategyData
    meta: MetaResponse
```

#### 4.4.4 Contributors Schema

```python
class ContributorItem(BaseModel):
    rank: int = Field(..., ge=1)
    position_id: int
    symbol: str
    underlying: str
    strategy_id: str | None = None
    quantity: int
    option_type: Literal["call", "put"]
    strike: float = Field(..., gt=0)
    expiry: str
    value_signed: float
    contribution_abs: float = Field(..., ge=0)
    contribution_pct: float = Field(..., ge=0, le=100)


class ContributorsData(BaseModel):
    metric: GreeksMetricEnum
    total_value: float
    total_abs_value: float = Field(..., ge=0)
    contributors: list[ContributorItem]


class ContributorsResponse(BaseModel):
    data: ContributorsData
    meta: MetaResponse
```

#### 4.4.5 History Schema

```python
class HistoryPoint(BaseModel):
    ts: datetime
    dollar_delta: float | None = None
    gamma_dollar: float | None = None
    vega_per_1pct: float | None = None
    theta_per_day: float | None = None
    coverage_pct: float | None = None


class HistoryData(BaseModel):
    scope: GreeksScopeEnum
    scope_id: str
    interval: IntervalEnum
    points: list[HistoryPoint]


class HistoryResponse(BaseModel):
    data: HistoryData
    meta: MetaResponse


class HistoryQueryParams(BaseModel):
    scope: GreeksScopeEnum = GreeksScopeEnum.ACCOUNT
    scope_id: str | None = None
    start_ts: datetime
    end_ts: datetime | None = None
    interval: IntervalEnum = IntervalEnum.FIVE_MIN
    metrics: list[GreeksMetricEnum] | None = None
```

#### 4.4.6 Alerts Schema

```python
class AlertItem(BaseModel):
    alert_id: str
    scope: GreeksScopeEnum
    scope_id: str
    metric: GreeksMetricEnum
    level: GreeksLevelEnum
    trigger_types: list[str]
    value_raw: float
    value_eval: float
    limit: float
    threshold: float
    utilization_pct: float = Field(..., ge=0)
    explains: list[str]
    is_recovery: bool = False
    created_at: datetime


class AlertsData(BaseModel):
    alerts: list[AlertItem]
    total_count: int = Field(..., ge=0)
    has_more: bool = False


class AlertsResponse(BaseModel):
    data: AlertsData
    meta: MetaResponse


class AlertsQueryParams(BaseModel):
    scope: GreeksScopeEnum | None = None
    scope_id: str | None = None
    metric: GreeksMetricEnum | None = None
    level: GreeksLevelEnum | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
```

#### 4.4.7 Limits Schema

```python
class ThresholdConfigItem(BaseModel):
    metric: GreeksMetricEnum
    direction: ThresholdDirectionEnum = ThresholdDirectionEnum.ABS
    limit: float = Field(..., gt=0)
    warn_pct: float = Field(0.80, ge=0, le=1)
    crit_pct: float = Field(1.00, ge=0, le=2)
    hard_pct: float = Field(1.20, ge=0, le=3)
    warn_recover_pct: float = Field(0.75, ge=0, le=1)
    crit_recover_pct: float = Field(0.90, ge=0, le=1)
    rate_window_seconds: int = Field(300, ge=60, le=3600)
    rate_change_pct: float = Field(0.20, ge=0, le=1)
    rate_change_abs: float = Field(0, ge=0)


class LimitsConfigData(BaseModel):
    scope: GreeksScopeEnum
    scope_id: str
    thresholds: dict[GreeksMetricEnum, ThresholdConfigItem]
    min_coverage_pct: float = Field(95.0, ge=0, le=100)
    dedupe_window_seconds: dict[GreeksLevelEnum, int]


class LimitsResponse(BaseModel):
    data: LimitsConfigData
    meta: MetaResponse


class LimitsUpdateRequest(BaseModel):
    thresholds: dict[GreeksMetricEnum, ThresholdConfigItem] | None = None
    min_coverage_pct: float | None = Field(None, ge=0, le=100)
    dedupe_window_seconds: dict[GreeksLevelEnum, int] | None = None
```

#### 4.4.8 WebSocket Schema

```python
class WSMeta(BaseModel):
    connection_id: str
    seq: int = Field(..., ge=0)
    server_ts: datetime
    as_of_ts: datetime | None = None
    as_of_ts_min: datetime | None = None
    as_of_ts_max: datetime | None = None
    staleness_seconds: int | None = Field(None, ge=0)


class WSConnectedData(BaseModel):
    account_id: str  # connection_id 只在 meta


class WSConnectedMessage(BaseModel):
    type: Literal["connected"] = "connected"
    data: WSConnectedData
    meta: WSMeta


class WSSubscribeOptions(BaseModel):
    include_strategies: bool = True
    strategy_ids: list[str] | None = None
    metrics: list[GreeksMetricEnum] | None = None
    throttle_ms: int = Field(1000, ge=100, le=60000)


class WSSubscribedData(BaseModel):
    channels: list[WSChannelType]
    options: WSSubscribeOptions


class WSSubscribedMessage(BaseModel):
    type: Literal["subscribed"] = "subscribed"
    data: WSSubscribedData
    meta: WSMeta


class WSSnapshotMessage(BaseModel):
    type: Literal["snapshot"] = "snapshot"
    channel: Literal["greeks"] = "greeks"
    data: SnapshotData
    meta: WSMeta


class WSStrategyUpdate(BaseModel):
    strategy_id: str
    dollar_delta: float | None = None
    gamma_dollar: float | None = None
    vega_per_1pct: float | None = None
    theta_per_day: float | None = None
    coverage_pct: float | None = None
    valid_legs_count: int | None = None
    total_legs_count: int | None = None
    levels: LevelsPatch | None = None
    utilization: UtilizationPatch | None = None
    deleted: bool = False


class WSAccountUpdate(BaseModel):
    dollar_delta: float | None = None
    gamma_dollar: float | None = None
    vega_per_1pct: float | None = None
    theta_per_day: float | None = None
    coverage_pct: float | None = None
    valid_legs_count: int | None = None
    total_legs_count: int | None = None
    levels: LevelsPatch | None = None
    utilization: UtilizationPatch | None = None


class WSUpdateData(BaseModel):
    account: WSAccountUpdate | None = None
    strategies: list[WSStrategyUpdate] | None = None


class WSUpdateMessage(BaseModel):
    type: Literal["update"] = "update"
    channel: Literal["greeks"] = "greeks"
    data: WSUpdateData
    meta: WSMeta


class WSAlertData(BaseModel):
    alert_id: str
    scope: GreeksScopeEnum
    scope_id: str
    metric: GreeksMetricEnum
    level: GreeksLevelEnum
    trigger_types: list[str]
    value_raw: float
    value_eval: float
    limit: float
    threshold: float
    utilization_pct: float = Field(..., ge=0)
    explains: list[str]
    is_recovery: bool = False


class WSAlertMessage(BaseModel):
    type: Literal["alert"] = "alert"
    channel: Literal["alerts"] = "alerts"
    data: WSAlertData
    meta: WSMeta


class WSPingMessage(BaseModel):
    type: Literal["ping"] = "ping"
    meta: WSMeta


class WSErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    details: dict | None = None
    meta: WSMeta


# 客户端消息
class WSAuthMessage(BaseModel):
    type: Literal["auth"] = "auth"
    token: str


class WSSubscribeMessage(BaseModel):
    type: Literal["subscribe"] = "subscribe"
    channels: list[WSChannelType]
    options: WSSubscribeOptions | None = None


class WSUnsubscribeMessage(BaseModel):
    type: Literal["unsubscribe"] = "unsubscribe"
    channels: list[WSChannelType]


class WSPongMessage(BaseModel):
    type: Literal["pong"] = "pong"
```

---

## 5. 前端架构

### 5.1 组件结构

```
frontend/src/features/greeks/
├── api/
│   ├── greeksApi.ts          # REST API 客户端
│   ├── greeksWsClient.ts     # WebSocket 客户端
│   └── types.ts              # 类型定义（从后端 schema 生成）
├── hooks/
│   ├── useGreeksSnapshot.ts  # 获取快照（REST + WS 混合）
│   ├── useGreeksHistory.ts   # 历史数据查询
│   ├── useGreeksAlerts.ts    # 告警数据
│   └── useGreeksWs.ts        # WebSocket 连接管理
├── components/
│   ├── GreeksDashboard/      # 主 Dashboard 容器
│   ├── GreeksCard/           # 单指标卡片
│   ├── GreeksTrend/          # 趋势图
│   ├── GreeksAlerts/         # 告警列表
│   └── GreeksContributors/   # 贡献度排名
├── store/
│   ├── greeksStore.ts        # Zustand store
│   ├── selectors.ts          # 派生数据选择器
│   └── wsIntegration.ts      # WS 事件桥接
└── utils/
    ├── formatters.ts         # 数值格式化
    └── constants.ts          # 常量定义
```

### 5.2 WebSocket 客户端

**设计要点：**
- 使用 `mitt` 替代 Node EventEmitter（避免构建兼容问题）
- 单例管理（避免多组件多连接）
- seq gap 时进入 `needsResync` 模式，丢弃 update 直到收到 snapshot
- 心跳：subscribed 后启动，任意消息刷新
- 重连：指数退避（1s→2s→4s→8s→16s），支持取消
- `manualClose` 标志防止主动断开后自动重连

**关键接口：**
```typescript
class GreeksWsClient {
  connect(): void;
  disconnect(): void;
  on<K extends keyof WSEvents>(event: K, handler: (data: WSEvents[K]) => void): void;
  off<K extends keyof WSEvents>(event: K, handler: (data: WSEvents[K]) => void): void;
  isConnected(): boolean;
  isResyncing(): boolean;
}

type WSEvents = {
  subscribed: { channels: string[]; options: any };
  snapshot: SnapshotData;      // 协议原始数据
  update: WSUpdateData;        // 协议原始数据
  alert: WSAlertData;
  wsError: { code: string; message: string };
  disconnected: { code: number; reason: string };
  resyncRequired: { reason: 'seq_gap' | 'queue_overflow' };
  stateChange: WSState;
};
```

**Deep Merge Patch 规则：**
- `null`/`undefined` 表示"字段未包含在 patch 中"，不覆盖
- 删除只能通过 tombstone (`deleted=true`)
- 只对 plain object 递归，Date/Array 直接覆盖

### 5.3 React Hooks

**useGreeksWs（单例）：** 管理 WS 连接，维护状态，分发事件

**useGreeksSnapshot：**
- 数据源优先级：WebSocket > REST
- WS 未连接或 resync 时启用 REST fallback
- 返回 `dataSource: 'websocket' | 'rest'` 标识

**useGreeksHistory：** 历史数据查询（TanStack Query）

**useGreeksAlerts：** 合并实时告警 + 历史告警（去重）

### 5.4 组件设计

**组件层次：**
```
GreeksDashboard
├── ConnectionStatus          # WS 连接状态
├── AccountSummary            # 账户汇总
│   ├── GreeksCard × 4        # Delta/Gamma/Vega/Theta
│   │   ├── UtilizationBar    # 限额进度条（阈值从 config 传入）
│   │   └── LevelBadge        # 告警级别徽章
│   └── CoverageIndicator
├── StrategyTabs              # 策略切换
├── GreeksTrend               # 趋势图
├── GreeksAlertPanel          # 告警面板
└── ContributorsPanel         # 贡献度
```

**UtilizationBar 阈值：** 从 `limitsConfig` 传入，不硬编码

### 5.5 状态管理（Zustand）

**Store 设计原则：**
- 使用 plain object 而非 Map/Set（便于序列化、DevTools）
- Deep merge patch（levels/utilization 按 key merge）
- 未知 strategy 的 patch 忽略（等待 snapshot）

**关键 State：**
```typescript
interface GreeksState {
  account: AccountGreeks | null;
  strategiesById: Record<string, StrategyGreeks>;
  alerts: AlertData[];
  connectionState: WSState;
  isResyncing: boolean;
  dataSource: 'websocket' | 'rest' | null;
  selectedStrategyId: string | null;
  expandedPanels: Record<string, boolean>;
}
```

**WS 集成规则：**
- WS Client emit 协议原始数据
- Store 负责数据结构转换和 patch 合并

---

## 6. 实施计划

### 6.1 开发阶段

| Phase | 时间 | 内容 |
|-------|------|------|
| P1: 核心后端 | Week 1-2 | Calculator + Aggregator + AlertEngine + Monitor |
| P2: API + 存储 | Week 3 | REST + WebSocket + TimescaleDB + Redis |
| P3: 前端 V1 | Week 4 | Dashboard + 告警面板 + E2E |
| P4: 集成上线 | Week 5 | RiskManager 集成 + 监控 + 灰度 |

### 6.2 Phase 1 任务

**P1.1 数据模型 + 迁移**
- 创建 greeks 模块目录
- 实现 Section 2 数据模型
- 创建 TimescaleDB 表 + 索引
- Alembic 迁移脚本

**P1.2 GreeksCalculator**
- IVCacheManager（Redis）
- Futu 数据获取
- BS + Bjerksund-Stensland 计算
- 单位规范化 + 质量校验
- 单元测试（覆盖率 > 90%）

**P1.3 Aggregator + AlertEngine**
- 单遍聚合 + coverage 计算
- 阈值评估 + ROC 检测
- is_breached / is_recovered
- level-scoped dedupe + escalation-through

**P1.4 GreeksMonitor**
- Single-flight refresh
- Graceful stop
- Aligned scheduling
- Send-side alert dedupe
- SnapshotStore + Redis publish

### 6.3 Phase 2 任务

**REST API：** snapshot / contributors / history / alerts / limits

**WebSocket：** 认证 + subscribe + snapshot/update 推送 + 心跳 + backpressure

**存储：** TimescaleDB 快照 + Redis IV 缓存

### 6.4 Phase 3 任务

**前端：** 类型生成 + WS Client + Store + Dashboard 组件 + E2E 测试

### 6.5 里程碑

| 里程碑 | 时间 | 交付物 |
|--------|------|--------|
| M1 | Week 2 | 后端核心 + 测试 |
| M2 | Week 3 | API + 存储 |
| M3 | Week 4 | 前端 V1 |
| M4 | Week 5 | 上线 |

### 6.6 风险

| 风险 | 缓解 |
|------|------|
| Futu Greeks 不准确 | Model fallback + 对比验证 |
| WS 连接数超限 | 单例管理 |
| 前端状态同步错误 | 完整测试 seq gap / resync |
| 告警风暴 | level-scoped dedupe + 回差 |

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
