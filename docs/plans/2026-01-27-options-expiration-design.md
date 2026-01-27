# Options Lifecycle - Expiration Alerts & Manual Handling (V1)

**设计文档版本**: 1.0
**创建日期**: 2026-01-27
**状态**: 已批准 - 可实施
**预计工期**: 10天 (1个完整迭代)

---

## 目录

1. [系统概览](#1-系统概览)
2. [数据模型设计](#2-数据模型设计)
3. [后端架构](#3-后端架构)
4. [前端架构](#4-前端架构)
5. [实施计划](#5-实施计划)

---

## 1. 系统概览

### 1.1 功能目标

实现期权生命周期管理的第一个垂直切片：**到期提醒 + 手动处理**。系统自动检测即将到期的期权持仓，按严重程度分级提醒，用户可以手动平仓或确认知晓。

**关键边界**：本系统在 V1 **不承担任何自动交易风险**。不包含自动平仓、自动行权、期权展期等功能。

### 1.2 用户流程

```
1. 系统检测 → 创建告警（7天/3天/1天/当天）
2. 用户在 /alerts 看到提醒 → 点击"去处理"
3. 跳转到 /options/expiring 专区 → 查看详情（自动滚动并高亮）
4. 用户选择：
   - 点击"平仓" → 创建卖出订单 → 持仓状态变更后从待处理列表移除
   - 点击"忽略" → Ack 告警 → 从待处理列表移除
```

### 1.3 核心原则

- **一个数据源，两种视图**：`GET /api/options/expiring` 同时服务两个页面
- **轻重分离**：`/alerts` 轻量展示，`/options/expiring` 完整操作
- **去重策略从硬编码升级为可配置系统**（平台能力提升）

### 1.4 检查触发机制

- **启动时立即检查**：系统启动后立即扫描一次（catch-up）
- **每天定时检查**：每天早上 8:00（按交易所时区，例如 America/New_York）
- **收盘前检查**：每天 15:00（最后操作机会）
- **手动触发 API**（仅限内部/测试）：`POST /api/options/check-expirations`

### 1.5 阈值与严重程度映射

| 剩余天数 (DTE) | 严重程度 | 前端渲染色 | 语义 |
|---|---|---|---|
| 7天内 | **INFO (SEV3)** | 蓝色 | 提前知晓 |
| 3天内 | **WARNING (SEV2)** | 黄色 | 需要关注 |
| 1天内 | **CRITICAL (SEV1)** | 红色 | 紧急处理 |
| 当天到期 | **CRITICAL (SEV1)** | 灰色 | 今日收盘到期 |

---

## 2. 数据模型设计

### 2.1 去重策略系统（平台能力升级）

**新增枚举类型**

```python
# backend/src/alerts/models.py

class DedupeStrategy(str, Enum):
    """Alert deduplication strategies.

    WINDOWED_10M: Group alerts within 10-minute windows (default)
    PERMANENT_PER_THRESHOLD: Dedupe permanently by threshold, no time window
    """
    WINDOWED_10M = "windowed_10m"
    PERMANENT_PER_THRESHOLD = "permanent_per_threshold"
```

**策略注册表（独立配置文件）**

```python
# backend/src/alerts/config.py (新建)

from src.alerts.models import AlertType, DedupeStrategy

# Alert type to deduplication strategy mapping
DEDUPE_STRATEGIES: dict[AlertType, DedupeStrategy] = {
    AlertType.OPTION_EXPIRING: DedupeStrategy.PERMANENT_PER_THRESHOLD,
    # All other types default to WINDOWED_10M
}

def get_dedupe_strategy(alert_type: AlertType) -> DedupeStrategy:
    """Get deduplication strategy for an alert type."""
    return DEDUPE_STRATEGIES.get(alert_type, DedupeStrategy.WINDOWED_10M)
```

### 2.2 新增 AlertType

```python
# backend/src/alerts/models.py - 在 AlertType 枚举中添加

class AlertType(str, Enum):
    # ... existing types ...

    # Options alerts
    OPTION_EXPIRING = "option_expiring"  # 期权即将到期
```

### 2.3 期权到期告警的数据结构

**Fingerprint 格式（使用 position_id）**

```python
# 格式: "option_expiring:{account_id}:{position_id}"
# 例如: "option_expiring:acc123:456"
```

**Dedupe Key 格式（无时间窗口）**

```python
# 格式: "{fingerprint}:threshold_{days}:permanent"
# 例如: "option_expiring:acc123:456:threshold_7:permanent"
# "permanent" 后缀便于数据库审计时识别非时间窗口告警
```

**Details 字段结构（V1 最小集）**

```python
# 必填字段
details = {
    "threshold_days": 7,          # 阈值天数 (7/3/1/0) - 必填
    "expiry_date": "2024-01-19",  # 到期日 (ISO format) - 必填
    "days_to_expiry": 7,          # 实际剩余天数 - 必填
    "position_id": 123,           # 持仓 ID - 必填
    "strike": 150.00,             # 行权价 (JSON number/float) - 必填
    "put_call": "call",           # put/call - 必填

    # 可选字段
    "quantity": 10,               # 合约数量
    "contract_key": "AAPL240119C150",  # OCC 标准合约标识
}
```

**Runtime 校验（带防御性日志）**

```python
import logging

logger = logging.getLogger(__name__)

def validate_option_expiring_details(details: dict) -> None:
    """验证 OPTION_EXPIRING 告警的必填字段"""
    required = ["threshold_days", "expiry_date", "days_to_expiry",
                "position_id", "strike", "put_call"]
    missing = [f for f in required if f not in details]
    if missing:
        position_id = details.get("position_id", "UNKNOWN")
        logger.error(
            f"OPTION_EXPIRING alert validation failed for position_id={position_id}: "
            f"missing fields={missing}"
        )
        raise ValueError(
            f"OPTION_EXPIRING alert missing required fields: {missing} "
            f"(position_id={position_id})"
        )
```

### 2.4 阈值表驱动配置

```python
# backend/src/options/expiration.py

from dataclasses import dataclass
from src.alerts.models import Severity

@dataclass
class ExpirationThreshold:
    """到期阈值配置（不含 UI 层 color）"""
    days: int                    # 剩余天数
    severity: Severity           # 告警级别

# 阈值表（升序排列：0天最紧急，7天最宽松）
EXPIRATION_THRESHOLDS = [
    ExpirationThreshold(days=0, severity=Severity.SEV1),  # 当天到期
    ExpirationThreshold(days=1, severity=Severity.SEV1),  # 1天内
    ExpirationThreshold(days=3, severity=Severity.SEV2),  # 3天内
    ExpirationThreshold(days=7, severity=Severity.SEV3),  # 7天内
]

# 最大阈值（用于统计"不在提醒范围内"）
MAX_THRESHOLD_DAYS = max(t.days for t in EXPIRATION_THRESHOLDS)

def get_applicable_thresholds(days_to_expiry: int) -> list[ExpirationThreshold]:
    """返回所有应触发的阈值（去重由 dedupe_key 保证）

    对于 DTE，返回所有 >= DTE 的阈值。系统会尝试为每个阈值创建告警，
    已发过的会被 dedupe_key 自动过滤。

    这种设计的好处：
    1. 启动时检查可以补发漏掉的阈值
    2. 重启后不会丢失应发的告警
    3. 多实例部署时行为一致

    示例：
    - DTE=10: 返回 []
    - DTE=6:  返回 [7天]
    - DTE=2:  返回 [3天, 7天]
    - DTE=1:  返回 [1天, 3天, 7天]
    - DTE=0:  返回 [0天, 1天, 3天, 7天]

    Args:
        days_to_expiry: 距离到期的天数（必须 >= 0）

    Returns:
        适用的阈值列表（按 days 升序）
    """
    return [t for t in EXPIRATION_THRESHOLDS if t.days >= days_to_expiry]
```

### 2.5 数据库约束与索引

**Migration 1: 告警去重唯一索引**

```sql
-- 添加 (type, dedupe_key) 复合唯一索引
-- 避免跨类型的 dedupe_key 冲突，更安全、更可演进
CREATE UNIQUE INDEX idx_alerts_type_dedupe_key ON alerts(type, dedupe_key);
```

**Migration 2: 幂等键表**

```sql
-- 幂等键持久化存储（TTL: 24小时）
CREATE TABLE idempotency_keys (
    key VARCHAR(255) PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    response_data JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);
```

**Migration 3: 性能索引**

```sql
-- 告警查询索引
CREATE INDEX idx_alerts_type_created ON alerts(type, created_at DESC);
CREATE INDEX idx_alerts_type_ack ON alerts(type, acknowledged)
  WHERE type = 'option_expiring';
CREATE INDEX idx_alerts_account_type ON alerts(entity_account_id, type);

-- 持仓查询索引（如果 positions 表未有）
CREATE INDEX idx_positions_asset_expiry ON positions(asset_type, expiry)
  WHERE asset_type = 'option';
```

### 2.6 修正后的 compute_dedupe_key 实现

```python
# backend/src/alerts/factory.py

import logging
from src.alerts.config import get_dedupe_strategy
from src.alerts.models import DedupeStrategy, RECOVERY_TYPES, AlertType

logger = logging.getLogger(__name__)

def compute_dedupe_key(alert: AlertEvent) -> str:
    """计算去重键（根据策略分发）"""

    # Recovery 类型特殊处理
    if alert.type in RECOVERY_TYPES:
        return f"{alert.fingerprint}:recovery:{alert.alert_id}"

    # 获取该 AlertType 的去重策略
    strategy = get_dedupe_strategy(alert.type)

    if strategy == DedupeStrategy.PERMANENT_PER_THRESHOLD:
        # 期权到期：永久去重，按阈值区分
        threshold_days = alert.details.get("threshold_days")
        position_id = alert.details.get("position_id", "UNKNOWN")

        if threshold_days is None:
            logger.error(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id}, alert_id={alert.alert_id})"
            )
            raise ValueError(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id})"
            )

        return f"{alert.fingerprint}:threshold_{threshold_days}:permanent"

    else:  # WINDOWED_10M (default)
        bucket = int(alert.event_timestamp.timestamp()) // (10 * 60)
        return f"{alert.fingerprint}:{bucket}"

def _build_fingerprint(
    alert_type: AlertType,
    account_id: str | None,
    symbol: str | None,
    strategy_id: str | None,
    details: dict[str, Any] | None = None,
) -> str:
    """构造 fingerprint（期权到期告警使用 position_id）"""

    # 期权到期告警：使用 position_id 构造 fingerprint（不包含 strategy_id）
    if alert_type == AlertType.OPTION_EXPIRING:
        position_id = details.get("position_id") if details else None
        if position_id is None:
            raise ValueError(
                "OPTION_EXPIRING alert requires 'position_id' in details"
            )
        # fingerprint 格式: "option_expiring:{account_id}:{position_id}"
        # 不包含 strategy_id，因为期权到期是 position 级别的事件
        return f"{alert_type.value}:{account_id or ''}:{position_id}"

    # 其他类型：保持原有逻辑
    return f"{alert_type.value}:{account_id or ''}:{symbol or ''}:{strategy_id or ''}"
```

---

## 3. 后端架构

### 3.1 模块结构

```
backend/src/
├── options/                    # 新增模块
│   ├── __init__.py
│   ├── expiration.py          # 阈值配置 + ExpirationChecker
│   ├── scheduler.py           # 定时任务调度器（分布式锁）
│   ├── models.py              # API Pydantic schemas
│   ├── idempotency.py         # 幂等性存储服务
│   └── metrics.py             # Prometheus metrics
├── alerts/
│   ├── config.py              # 新增：去重策略配置
│   ├── factory.py             # 修改：compute_dedupe_key
│   └── ... (existing)
├── api/
│   └── options.py             # 新增：期权相关 API endpoints
└── core/
    └── portfolio.py           # 已有：PortfolioManager
```

### 3.2 核心组件：ExpirationChecker

```python
# backend/src/options/expiration.py

import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from uuid import uuid4

from src.alerts.factory import create_alert
from src.alerts.models import AlertType
from src.alerts.repository import AlertRepository
from src.core.portfolio import PortfolioManager
from src.models.position import AssetType
from src.options.metrics import (
    expiration_check_runs_total,
    alerts_created_total,
    alerts_deduped_total,
    check_errors_total,
    check_duration_seconds,
)

logger = logging.getLogger(__name__)

class ExpirationChecker:
    """期权到期检查器

    职责：
    1. 扫描所有期权持仓
    2. 计算距离到期天数（DTE）
    3. 根据阈值表生成告警
    4. 利用 dedupe_key 实现幂等写入
    """

    def __init__(
        self,
        portfolio: PortfolioManager,
        alert_repo: AlertRepository,
        market_tz: ZoneInfo = ZoneInfo("America/New_York"),
    ):
        self.portfolio = portfolio
        self.alert_repo = alert_repo
        self.market_tz = market_tz

    @check_duration_seconds.time()
    async def check_expirations(self, account_id: str) -> dict:
        """检查期权到期并生成告警

        Returns:
            检查结果统计
        """
        run_id = str(uuid4())
        logger.info(f"Starting expiration check run_id={run_id} account={account_id}")

        stats = {
            "run_id": run_id,
            "positions_checked": 0,
            "positions_skipped_missing_expiry": 0,
            "positions_already_expired": 0,
            "positions_not_expiring_soon": 0,
            "alerts_attempted": 0,
            "alerts_created": 0,
            "alerts_deduplicated": 0,
            "errors": [],
        }

        try:
            # 获取所有期权持仓
            positions = await self.portfolio.get_positions(account_id=account_id)
            option_positions = [p for p in positions if p.asset_type == AssetType.OPTION]

            # 使用市场时区计算"今天"
            today = datetime.now(self.market_tz).date()
            logger.info(
                f"run_id={run_id} checking {len(option_positions)} option positions "
                f"relative to {today} ({self.market_tz})"
            )

            for pos in option_positions:
                stats["positions_checked"] += 1

                try:
                    # 数据校验：缺失 expiry
                    if pos.expiry is None:
                        error_msg = (
                            f"Position {pos.id} (symbol={pos.symbol}) missing expiry date"
                        )
                        logger.warning(f"run_id={run_id} {error_msg}")
                        stats["positions_skipped_missing_expiry"] += 1
                        stats["errors"].append(error_msg)
                        check_errors_total.labels(error_type="missing_expiry").inc()
                        continue

                    # 计算 DTE
                    days_to_expiry = (pos.expiry - today).days

                    # 跳过已过期
                    if days_to_expiry < 0:
                        stats["positions_already_expired"] += 1
                        logger.debug(f"run_id={run_id} position {pos.id} already expired")
                        continue

                    # 获取适用的阈值
                    thresholds = get_applicable_thresholds(days_to_expiry)

                    if not thresholds:
                        stats["positions_not_expiring_soon"] += 1
                        logger.debug(f"run_id={run_id} position {pos.id} DTE={days_to_expiry} out of scope")
                        continue

                    # 为每个阈值尝试创建告警
                    for threshold in thresholds:
                        stats["alerts_attempted"] += 1

                        try:
                            alert = self._create_expiration_alert(
                                position=pos,
                                threshold=threshold,
                                days_to_expiry=days_to_expiry,
                                account_id=account_id,
                            )

                            # 幂等写入
                            is_new, alert_id = await self.alert_repo.persist_alert(alert)

                            if is_new:
                                stats["alerts_created"] += 1
                                alerts_created_total.inc()
                                logger.info(
                                    f"run_id={run_id} created alert: "
                                    f"position_id={pos.id} symbol={pos.symbol} "
                                    f"DTE={days_to_expiry} threshold={threshold.days}d "
                                    f"alert_id={alert_id}"
                                )
                            else:
                                stats["alerts_deduplicated"] += 1
                                alerts_deduped_total.inc()
                                logger.debug(
                                    f"run_id={run_id} alert deduplicated: "
                                    f"position_id={pos.id} threshold={threshold.days}d"
                                )

                        except Exception as e:
                            error_msg = (
                                f"Failed to create alert for position_id={pos.id} "
                                f"threshold={threshold.days}d: {e}"
                            )
                            logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                            stats["errors"].append(error_msg)
                            check_errors_total.labels(error_type="alert_creation").inc()

                except Exception as e:
                    error_msg = f"Failed to process position_id={pos.id}: {e}"
                    logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                    stats["errors"].append(error_msg)
                    check_errors_total.labels(error_type="position_processing").inc()

            logger.info(
                f"run_id={run_id} check complete: "
                f"{stats['positions_checked']} checked, "
                f"{stats['alerts_created']} created, "
                f"{stats['alerts_deduplicated']} deduplicated, "
                f"{len(stats['errors'])} errors"
            )

            expiration_check_runs_total.labels(status="success").inc()
            return stats

        except Exception as e:
            logger.error(f"run_id={run_id} check failed", exc_info=True)
            expiration_check_runs_total.labels(status="failed").inc()
            raise

    def _create_expiration_alert(
        self,
        position,
        threshold: ExpirationThreshold,
        days_to_expiry: int,
        account_id: str,
    ):
        """构造期权到期告警"""

        # 数据校验
        if position.strike is None:
            raise ValueError(f"Position {position.id} missing strike price")
        if position.put_call is None:
            raise ValueError(f"Position {position.id} missing put_call type")

        # 构造 summary
        if days_to_expiry == 0:
            summary = f"期权 {position.symbol} 今日收盘到期"
        elif days_to_expiry == 1:
            summary = f"期权 {position.symbol} 明日到期"
        else:
            summary = f"期权 {position.symbol} 将在 {days_to_expiry} 天后到期"

        # 构造 details
        strike_value = float(position.strike) if isinstance(position.strike, Decimal) else position.strike

        details = {
            "threshold_days": threshold.days,
            "expiry_date": position.expiry.isoformat(),
            "days_to_expiry": days_to_expiry,
            "position_id": position.id,
            "strike": strike_value,
            "put_call": position.put_call.value,
            "quantity": position.quantity,
        }

        if hasattr(position, 'contract_key') and position.contract_key:
            details["contract_key"] = position.contract_key

        # 创建告警（symbol 保留真实期权标识符用于展示）
        return create_alert(
            type=AlertType.OPTION_EXPIRING,
            severity=threshold.severity,
            summary=summary,
            account_id=account_id,
            symbol=position.symbol,
            details=details,
        )
```

### 3.3 定时任务调度器（多实例安全）

```python
# backend/src/options/scheduler.py

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

class ExpirationScheduler:
    """期权到期检查调度器

    部署策略（二选一）：
    1. 单副本部署（推荐）：scheduler 独立服务，只部署一个实例
    2. 分布式锁：使用 Postgres advisory lock 或 Redis lock
    """

    def __init__(
        self,
        checker,
        account_id: str,
        market_tz: ZoneInfo = ZoneInfo("America/New_York"),
        use_distributed_lock: bool = False,
    ):
        self.checker = checker
        self.account_id = account_id
        self.market_tz = market_tz
        self.use_distributed_lock = use_distributed_lock
        self.scheduler = AsyncIOScheduler(timezone=market_tz)

    async def _run_check_with_lock(self):
        """带分布式锁的检查执行"""
        if self.use_distributed_lock:
            # 使用 Postgres advisory lock
            lock_acquired = await self._try_acquire_lock()
            if not lock_acquired:
                logger.info("Expiration check skipped: another instance is running")
                return {"executed": False, "reason": "lock_held_by_another_instance"}

            try:
                stats = await self.checker.check_expirations(self.account_id)
                stats["executed"] = True
                return stats
            finally:
                await self._release_lock()
        else:
            # 单副本部署，直接执行
            stats = await self.checker.check_expirations(self.account_id)
            stats["executed"] = True
            return stats

    async def _try_acquire_lock(self) -> bool:
        """尝试获取分布式锁（Postgres advisory lock 示例）"""
        # 使用 position_id hash 作为 lock key
        lock_key = hash("expiration_check") % (2**31)

        # SELECT pg_try_advisory_lock(lock_key)
        # 返回 True 表示成功获取锁
        # 这里需要注入 DB session
        pass

    async def _release_lock(self):
        """释放分布式锁"""
        # SELECT pg_advisory_unlock(lock_key)
        pass

    def start(self):
        """启动调度器"""

        # 启动时立即检查一次
        logger.info("Scheduling immediate expiration check on startup")
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger='date',
            run_date=datetime.now(self.market_tz),
            id='startup_check',
        )

        # 每天早上 8:00（市场开盘前）
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger=CronTrigger(hour=8, minute=0, timezone=self.market_tz),
            id='daily_morning_check',
        )

        # 每天 15:00（收盘前，最后操作机会）
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger=CronTrigger(hour=15, minute=0, timezone=self.market_tz),
            id='daily_closing_check',
        )

        self.scheduler.start()
        logger.info("ExpirationScheduler started")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("ExpirationScheduler shut down")
```

### 3.4 幂等性服务

```python
# backend/src/options/idempotency.py

import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

class IdempotencyService:
    """幂等键持久化存储（TTL: 24小时）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def store_key(
        self,
        key: str,
        resource_type: str,
        resource_id: str,
        response_data: dict,
        ttl_hours: int = 24,
    ) -> None:
        """存储幂等键和响应数据"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        sql = text("""
            INSERT INTO idempotency_keys (key, resource_type, resource_id, response_data, expires_at)
            VALUES (:key, :resource_type, :resource_id, :response_data, :expires_at)
            ON CONFLICT (key) DO NOTHING
        """)

        await self.session.execute(sql, {
            "key": key,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "response_data": json.dumps(response_data),
            "expires_at": expires_at,
        })
        await self.session.commit()

    async def get_cached_response(self, key: str) -> tuple[bool, dict | None]:
        """获取缓存的响应数据

        Returns:
            (exists, response_data)
        """
        sql = text("""
            SELECT response_data
            FROM idempotency_keys
            WHERE key = :key AND expires_at > NOW()
        """)

        result = await self.session.execute(sql, {"key": key})
        row = result.fetchone()

        if row is None:
            return (False, None)

        response_data = json.loads(row[0])
        return (True, response_data)

    async def cleanup_expired(self) -> int:
        """清理过期的幂等键（定期任务调用）"""
        sql = text("""
            DELETE FROM idempotency_keys
            WHERE expires_at <= NOW()
        """)

        result = await self.session.execute(sql)
        await self.session.commit()
        return result.rowcount
```

### 3.5 API 实现

```python
# backend/src/api/options.py

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.options.models import ExpiringAlertsResponse, ClosePositionRequest, ClosePositionResponse
from src.options.idempotency import IdempotencyService
from src.core.portfolio import PortfolioManager
from src.orders.service import OrderService

router = APIRouter(prefix="/api/options", tags=["options"])

@router.get("/expiring", response_model=ExpiringAlertsResponse)
async def get_expiring_alerts(
    account_id: str,
    status: str = "pending",  # pending | acknowledged | all
    sort_by: str = "dte",  # dte | severity | expiry
    session: AsyncSession = Depends(get_session),
):
    """获取即将到期的期权告警列表

    **返回粒度**：按 alert 粒度（唯一键 alert_id）
    同一 position 可能有多个阈值告警（7/3/1/0天）
    """
    # 查询 alerts 表，JOIN positions 表获取估值信息
    # 按 alert 粒度返回，包含 position 信息用于展示和操作
    pass

@router.post("/{position_id}/close", response_model=ClosePositionResponse)
async def close_position(
    position_id: int,
    request: ClosePositionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
):
    """平仓期权持仓（幂等 + 事务保障）

    数据库事务：
    1. 调用交易引擎卖出
    2. 标记 Position 状态
    3. 批量 Resolve 相关 Alerts

    幂等性：
    - 同 Idempotency-Key 重复请求返回缓存结果（200）
    - 不同 Key 正常创建新订单

    错误码：
    - 200: 成功创建订单或返回缓存结果
    - 409: 该持仓已有进行中的平仓请求
    - 404: 持仓不存在
    - 403: 持仓当前无法平仓
    """
    idempotency_service = IdempotencyService(session)

    # 检查幂等键
    exists, cached_response = await idempotency_service.get_cached_response(idempotency_key)
    if exists:
        return cached_response

    # 开始数据库事务
    async with session.begin():
        try:
            # 1. 获取持仓
            portfolio = PortfolioManager(...)
            position = await portfolio.get_position_by_id(position_id)
            if not position:
                raise HTTPException(status_code=404, detail="Position not found")

            if position.asset_type != AssetType.OPTION:
                raise HTTPException(status_code=400, detail="Not an option position")

            # 检查是否可平仓
            if not position.is_closable:
                raise HTTPException(
                    status_code=403,
                    detail="Position cannot be closed (may be in settlement)"
                )

            # 2. 创建卖出订单
            order_service = OrderService(...)
            order = await order_service.create_sell_order(
                position=position,
                reason=request.reason,
            )

            # 3. 标记 Position 状态
            await portfolio.mark_position_closing(position_id)

            # 4. 批量 Resolve 相关 Alerts
            await alert_repo.resolve_alerts_for_position(position_id)

            # 构造响应
            response = ClosePositionResponse(
                success=True,
                order_id=order.id,
                message=f"Close order created for position {position_id}",
            )

            # 存储幂等键
            await idempotency_service.store_key(
                key=idempotency_key,
                resource_type="close_position",
                resource_id=str(position_id),
                response_data=response.dict(),
            )

            return response

        except Exception as e:
            # 事务回滚
            await session.rollback()
            raise

@router.post("/check-expirations")
async def trigger_manual_check(
    account_id: str,
    session: AsyncSession = Depends(get_session),
):
    """手动触发到期检查（仅内部/测试使用）"""
    checker = ExpirationChecker(...)
    stats = await checker.check_expirations(account_id)
    return stats
```

---

## 4. 前端架构

### 4.1 两个页面的职责分工

```
/alerts (统一告警入口)
├── 显示所有类型告警（包括期权到期）
├── 按 severity 排序
├── 对 OPTION_EXPIRING 轻量增强：
│   ├── 显示关键字段：DTE、expiry、strike、P/C
│   └── "去处理"按钮 → deep link 到 /options/expiring?alert_id=X
└── 不包含完整操作流程（避免杂货铺）

/options/expiring (期权专区)
├── 聚合视图：按 expiry/DTE 分组
├── URL 参数支持：?alert_id=X（自动滚动并高亮对应行）
├── 过滤器：账户、策略、DTE 范围、状态
├── 完整操作：
│   ├── "平仓"按钮 → 确认弹窗 → 幂等请求创建卖出订单
│   └── "忽略"按钮 → Ack 告警 → 从待处理列表移除
└── 默认显示"未 Ack"，已忽略可筛选，空状态友好提示
```

### 4.2 共享 API 设计

**核心 API：GET /api/options/expiring**

```typescript
// Request
interface ExpiringAlertsQuery {
  account_id: string;
  status?: "pending" | "acknowledged" | "all";
  sort_by?: "dte" | "severity" | "expiry";
}

// Response - 按 alert 粒度返回
interface ExpiringAlertRow {
  // 告警信息（主键）
  alert_id: string;
  severity: "critical" | "warning" | "info";
  threshold_days: number;
  created_at: string;
  acknowledged: boolean;
  acknowledged_at?: string;

  // 持仓信息
  position_id: number;
  symbol: string;
  strike: number;
  put_call: "put" | "call";
  expiry_date: string;
  quantity: number;

  // 到期信息
  days_to_expiry: number;

  // 估值（可选）
  current_price?: number;
  market_value?: number;
  unrealized_pnl?: number;

  // 可操作性
  is_closable: boolean;
}

interface ExpiringAlertsResponse {
  alerts: ExpiringAlertRow[];  // 按 alert 粒度
  total: number;
  summary: {
    critical_count: number;
    warning_count: number;
    info_count: number;
  };
}
```

### 4.3 前端组件设计

**关键实现要点**：

1. **Deep Link 增强**：`?alert_id=X` 触发自动滚动和高亮闪烁（2秒）
2. **列表 Key**：使用 `alert_id` 而非 `position_id`（同 position 可能有多条告警）
3. **幂等请求**：close 操作自动生成 `Idempotency-Key`（UUID）
4. **空状态友好**：显示"目前没有即将到期的期权，喝杯咖啡吧 ☕"
5. **左侧色条**：表格行用左侧 4px 色条表示严重程度，不改变背景色
6. **DTE 格式化**：0天显示"今日收盘到期"，1天显示"明日到期"

详细实现见附录 A。

---

## 5. 实施计划

### 5.1 实施顺序（10天完整迭代）

**Phase 1: 基础设施（Day 1-2）**

- 3个数据库 migrations（唯一索引、幂等键表、性能索引）
- Alerts 平台能力升级（去重策略系统）
- 回归测试：确保旧类型告警不受影响

**Phase 2: 期权到期检查核心（Day 3-4）**

- ExpirationChecker 实现
- 单元测试（修正测试期望值：DTE=1 → 3条告警）
- 集成测试（事务一致性）

**Phase 3: 定时任务 + API（Day 5-7）**

- 调度器实现（**必须明确多实例策略**：单副本 or 分布式锁）
- 幂等性服务实现（持久化到 DB，TTL 24小时）
- API 实现（close 使用事务：订单+状态+告警）
- API 测试（幂等性、错误码、事务回滚）

**Phase 4: 前端实现（Day 8-9）**

- 生成类型定义
- 期权专区页面（deep link + 滚动定位）
- Alerts 页面增强
- API 客户端（自动生成幂等键）

**Phase 5: 端到端验证（Day 10）**

- 完整流程验证（修正期望值）
- 边界情况验证
- 多实例并发测试

### 5.2 关键文件清单

**后端新增**：
- `alerts/config.py`
- `options/expiration.py`
- `options/scheduler.py`
- `options/models.py`
- `options/idempotency.py`
- `options/metrics.py`
- `api/options.py`
- 3个 alembic migrations

**后端修改**：
- `alerts/models.py`
- `alerts/factory.py`
- `main.py`

**前端新增**：
- `pages/OptionsExpiringPage.tsx`
- `components/options/ExpiringAlertsList.tsx`
- `components/options/ThresholdBadge.tsx`
- `components/options/PutCallBadge.tsx`
- `api/options.ts`

**前端修改**：
- `components/alerts/AlertRow.tsx`
- `App.tsx`

### 5.3 测试覆盖要求

**必须通过的测试**：

1. **阈值匹配逻辑**（修正期望值）
   - DTE=1 → 3条告警（1/3/7）
   - DTE=0 → 4条告警（0/1/3/7）

2. **幂等性持久化**
   - 同 key 重复请求 → 返回缓存结果
   - 重启后仍有效

3. **事务原子性**
   - 订单创建失败 → alerts 不变

4. **多实例安全**
   - 两个实例同时运行 → 只有一个执行

5. **回归测试**
   - 旧类型告警不受影响
   - details=None 时不崩溃

### 5.4 部署检查清单

**部署前**：
- [ ] 所有测试通过
- [ ] 3个 migrations 测试环境验证
- [ ] **确认 scheduler 部署策略**（单副本 or 锁）
- [ ] Idempotency-Key 在 gateway 层传递
- [ ] 性能测试：1000 持仓 < 10s
- [ ] Prometheus metrics 导出准备

**部署后**：
- [ ] 访问 /options/expiring 页面正常
- [ ] 手动触发检查，观察 run_id 日志
- [ ] Deep link 跳转 + 高亮 + 滚动正常
- [ ] 平仓幂等性测试（快速双击）
- [ ] **验证多实例场景**（日志确认只有一个执行）
- [ ] 次日 8:00 验证定时任务执行
- [ ] Metrics dashboard 趋势正常

### 5.5 性能目标

- 1000 个期权持仓检查 < 10s
- GET /api/options/expiring < 500ms (P95)
- POST close < 1s (P95)
- 幂等键查询 < 50ms (P95)

### 5.6 可观测性（Prometheus Metrics）

```
options_expiration_check_runs_total{status="success|failed|skipped"}
options_expiration_alerts_created_total
options_expiration_alerts_deduped_total
options_expiration_check_errors_total{error_type="..."}
options_expiration_check_duration_seconds
options_expiration_pending_alerts
```

### 5.7 回滚计划

- 前端回滚：简单（静态资源回滚）
- 后端回滚：停止 scheduler，保留已有告警数据
- **不建议回滚 migrations**（索引、幂等表无副作用）
- **生产环境禁止直接 DELETE alerts**（使用软删除）

### 5.8 后续优化方向（V2+）

- 自动平仓策略（ITM/OTM 判断）
- 期权展期（Roll）功能
- 批量操作（一键忽略）
- 多渠道通知（邮件/Slack/Telegram）
- 历史到期统计分析
- Greeks 监控集成
- 行权预期股票持仓自动创建
- 周期权专门阈值配置

---

## 附录 A：前端组件详细实现

### A.1 期权专区页面核心代码

```typescript
// frontend/src/pages/OptionsExpiringPage.tsx

function OptionsExpiringPage() {
  const [searchParams] = useSearchParams();
  const highlightAlertId = searchParams.get("alert_id");

  // Deep Link 高亮动画
  useEffect(() => {
    if (highlightAlertId) {
      const element = document.getElementById(`alert-${highlightAlertId}`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "center" });
        element.classList.add("highlight-flash");
        setTimeout(() => element.classList.remove("highlight-flash"), 2000);
      }
    }
  }, [highlightAlertId, data]);

  // 平仓操作（自动生成幂等键）
  const closeMutation = useMutation({
    mutationFn: ({ position_id }: { position_id: number }) =>
      api.options.closePosition(position_id, {
        headers: { "Idempotency-Key": uuidv4() }
      }),
  });

  // ...
}
```

### A.2 列表组件（按 alert 粒度）

```typescript
// frontend/src/components/options/ExpiringAlertsList.tsx

function ExpiringAlertsList({ alerts, onClose, onAck }) {
  const grouped = groupBy(alerts, (alert) => alert.expiry_date);

  return (
    <div className="expiring-alerts-list">
      {sortedDates.map((date) => (
        <div key={date} className="expiry-group">
          <h3>{formatDate(date)} ({formatDaysToExpiry(dte)})</h3>

          <table>
            <tbody>
              {grouped[date].map((alert) => (
                <tr
                  key={alert.alert_id}  // 使用 alert_id 作为 key
                  id={`alert-${alert.alert_id}`}
                  className={`alert-row severity-${alert.severity}`}
                >
                  <td className="severity-stripe">
                    <div className={`stripe stripe-${alert.severity}`} />
                  </td>

                  {/* 其他列 */}

                  <td className="actions">
                    {alert.is_closable && (
                      <button onClick={() => onClose(alert)}>平仓</button>
                    )}
                    {!alert.acknowledged && (
                      <button onClick={() => onAck(alert)}>忽略</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
```

### A.3 CSS 样式

```css
/* 高亮闪烁动画 */
.alert-row.highlight-flash {
  animation: highlight-pulse 2s ease-in-out;
}

@keyframes highlight-pulse {
  0%, 100% { background-color: transparent; }
  50% { background-color: rgba(59, 130, 246, 0.2); }
}

/* 左侧色条 */
.severity-stripe {
  padding: 0;
  width: 4px;
}

.stripe {
  width: 4px;
  height: 100%;
}

.stripe-critical { background-color: #ef4444; }
.stripe-warning { background-color: #f59e0b; }
.stripe-info { background-color: #3b82f6; }
```

---

## 附录 B：关键决策记录

### B.1 为什么采用"按 alert 粒度"返回 API？

**原因**：
1. 同一 position 可能有多个阈值告警（7/3/1/0天）
2. 每个告警有独立的 alert_id、created_at、acknowledged 状态
3. 前端列表需要独立显示和操作每条告警

**替代方案**（不采用）：按 position 聚合，包含 alerts 数组
- 复杂度更高
- 前端需要拆解和重组数据

### B.2 为什么 fingerprint 不包含 strategy_id？

**原因**：
- 期权到期是 **position 级别**的事件，与 strategy 无关
- 同一 position 不应因 strategy_id 变化而重复提醒
- 简化 fingerprint 结构

### B.3 为什么幂等键需要持久化到 DB？

**原因**：
1. 平仓涉及资产销账，重复下单风险极高
2. 内存方案重启后失效
3. 24小时 TTL 覆盖绝大部分重试场景

### B.4 为什么需要多实例安全策略？

**原因**：
1. 生产环境通常多副本部署
2. 没有协调机制会导致重复检查、告警重复、日志爆炸
3. 两种方案：单副本（简单）或分布式锁（灵活）

---

**文档结束**
