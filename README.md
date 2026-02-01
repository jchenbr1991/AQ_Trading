# AQ Trading

全栈算法交易系统，支持美股、期权、期货交易。

## 功能特性

- **交易核心**：Portfolio Manager、Strategy Engine、Risk Manager、Order Manager
- **回测引擎**：历史数据回测、基准对比、Sharpe/Alpha/Beta 计算
- **Greeks 监控**：期权 Delta/Gamma/Theta/Vega 实时追踪
- **衍生品管理**：期权到期追踪、期货自动换月
- **AI 代理系统**：Researcher、Analyst、Risk Controller、Ops 四类 AI 代理
- **健康监控**：多层心跳检测、优雅降级、自动恢复
- **仪表盘**：React + TypeScript 实时监控界面

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11+, FastAPI, SQLAlchemy |
| 前端 | TypeScript 5.3+, React, TanStack Query, Tailwind |
| 数据库 | PostgreSQL (TimescaleDB), Redis |
| 券商 | Futu (moomoo) OpenAPI |

## 快速开始

### 前置要求

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose

### 1. 克隆仓库

```bash
git clone https://github.com/jchenbr1991/AQ_Trading.git
cd AQ_Trading
```

### 2. 启动基础设施

```bash
# 启动 PostgreSQL (TimescaleDB) 和 Redis
docker-compose up -d

# 验证服务状态
docker-compose ps
```

### 3. 安装后端依赖

```bash
cd backend

# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -e ".[dev]"
```

### 4. 配置环境变量

```bash
# 在 backend 目录创建 .env 文件 (仍在 backend 目录中)
cat > .env << EOF
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/aq_trading
REDIS_URL=redis://localhost:6379/0
FUTU_HOST=127.0.0.1
FUTU_PORT=11111
DEBUG=true
EOF
```

### 5. 初始化数据库

```bash
# 运行数据库迁移 (仍在 backend 目录中)
alembic upgrade head
```

### 6. 启动后端服务

```bash
# 启动后端 (仍在 backend 目录中)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

后端 API 文档: http://localhost:8000/docs

### 7. 安装并启动前端

```bash
# 新开终端，进入前端目录
cd frontend
npm install
npm run dev
```

仪表盘: http://localhost:5173

## 项目结构

```
aq_trading/
├── backend/                 # Python 后端
│   ├── src/
│   │   ├── main.py         # FastAPI 入口
│   │   ├── api/            # REST API 路由
│   │   ├── backtest/       # 回测引擎
│   │   ├── broker/         # 券商接口
│   │   ├── core/           # 核心业务逻辑
│   │   ├── derivatives/    # 衍生品管理
│   │   ├── greeks/         # Greeks 计算
│   │   ├── health/         # 健康监控
│   │   ├── risk/           # 风险管理
│   │   ├── strategies/     # 策略引擎
│   │   └── workers/        # 后台任务
│   ├── config/             # 配置文件
│   ├── tests/              # 测试
│   └── pyproject.toml
│
├── frontend/               # React 前端
│   ├── src/
│   │   ├── pages/          # 页面组件
│   │   ├── components/     # UI 组件
│   │   ├── hooks/          # React Hooks
│   │   └── api/            # API 客户端
│   └── package.json
│
├── agents/                 # AI 代理系统
│   ├── prompts/            # 代理提示词
│   ├── tools/              # 代理工具
│   │   ├── backtest.py     # 回测工具
│   │   ├── market_data.py  # 行情数据
│   │   ├── portfolio.py    # 持仓查询
│   │   ├── redis_writer.py # Redis 写入
│   │   └── reconciliation.py # 对账工具
│   ├── dispatcher.py       # 代理调度器
│   └── permissions.py      # 权限模型
│
├── specs/                  # 功能规格文档
├── docs/                   # 设计文档
│
├── docker-compose.yml      # Docker 编排 (PostgreSQL + Redis)
├── ARCHITECTURE.md         # 技术架构文档
├── STRATEGY.md             # 产品策略与开发路线
├── BACKLOG.md              # 开发进度
├── AGENTS.md               # AI 代理说明
├── CLAUDE.md               # Claude Code 使用指南
└── GEMINI.md               # Gemini 使用指南
```

## 运行测试

```bash
# 后端测试 (在 backend 目录)
cd backend
pytest -v

# 前端测试 (在 frontend 目录)
cd ../frontend
npm test

# AI 代理测试 (在项目根目录)
cd ..
python -m pytest agents/tests/ -v
```

## 配置说明

### 风险参数 (`backend/config/risk.yaml`)

```yaml
risk:
  max_position_value: 10000    # 单个持仓最大金额
  max_position_pct: 5          # 单个持仓最大占比 (%)
  max_positions: 20            # 最大持仓数量
  daily_loss_limit: 1000       # 日亏损限额
  max_drawdown_pct: 10         # 最大回撤 (%)
```

### 策略配置 (`backend/config/strategies.yaml`)

```yaml
strategies:
  momentum:
    lookback_period: 20
    entry_threshold: 0.02
    exit_threshold: -0.01
```

### 衍生品配置 (`backend/config/derivatives.yaml`)

```yaml
derivatives:
  warning_days: 5              # 到期预警天数
  roll_days_before_expiry: 5   # 换月提前天数
```

## API 端点概览

| 端点 | 描述 |
|------|------|
| `GET /health` | 健康检查 |
| `GET /api/portfolio/positions` | 获取持仓 |
| `GET /api/portfolio/summary` | 账户概览 |
| `POST /api/backtest` | 运行回测 |
| `GET /api/greeks` | Greeks 数据 |
| `GET /api/derivatives/expiring` | 到期合约 |
| `POST /api/agents/invoke` | 调用 AI 代理 |
| `GET /api/health/detailed` | 详细健康状态 |

完整 API 文档访问: http://localhost:8000/docs

## AI 代理系统

系统包含四类 AI 代理:

| 代理 | 职责 | 工具权限 |
|------|------|----------|
| **Researcher** | 策略优化、参数调优 | backtest, market_data |
| **Analyst** | 情绪分析、因子生成 | market_data, sentiment 写入 |
| **Risk Controller** | 动态风险调整 | portfolio, risk_bias 写入 |
| **Ops** | 运维、对账分析 | reconciliation, portfolio |

### 调用代理

```bash
curl -X POST http://localhost:8000/api/agents/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "role": "researcher",
    "task": "Analyze momentum strategy performance"
  }'
```

## 开发指南

### 添加新策略

1. 在 `backend/src/strategies/examples/` 创建策略文件
2. 继承 `BaseStrategy` 类
3. 实现 `on_market_data()` 方法
4. 在 `config/strategies.yaml` 添加配置
5. 回测验证后移至 `strategies/live/`

### 添加新 API 端点

1. 在 `backend/src/api/` 创建路由文件
2. 定义 Pydantic 模型
3. 在 `main.py` 注册路由
4. 添加测试

## 生产部署

### 环境变量

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/aq_trading
REDIS_URL=redis://host:6379/0
FUTU_HOST=futu-opend-host
FUTU_PORT=11111
DEBUG=false
```

### 安全提示

- 生产环境务必设置 `DEBUG=false`
- 妥善保管 Futu API 凭证
- 使用强密码配置 PostgreSQL 和 Redis
- 建议在隔离网络环境中运行

## 许可证

MIT License

## 相关文档

- [技术架构](./ARCHITECTURE.md) - 详细系统架构设计
- [产品策略](./STRATEGY.md) - 开发路线与组件设计
- [开发进度](./BACKLOG.md) - 功能实现状态
- [AI 代理说明](./AGENTS.md) - AI 代理系统详解
- [Claude Code 指南](./CLAUDE.md) - Claude Code 使用规范
- [Gemini 指南](./GEMINI.md) - Gemini 使用说明
