# Quickstart: AQ Trading

**Branch**: `001-product-overview` | **Date**: 2026-01-31

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ with TimescaleDB extension
- Redis 7+
- Docker & Docker Compose (recommended)
- Futu OpenAPI account and credentials

---

## 1. Clone & Setup

```bash
# Clone repository
git clone <repository-url>
cd aq_trading

# Create Python virtual environment
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install backend dependencies
pip install -e ".[dev]"

# Install frontend dependencies
cd ../frontend
npm install
```

---

## 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Database
POSTGRES_URL=postgresql+asyncpg://user:password@localhost:5432/aq_trading
DATABASE_URL=postgresql://user:password@localhost:5432/aq_trading

# Redis
REDIS_URL=redis://localhost:6379

# Futu OpenAPI
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# Trading
DEFAULT_ACCOUNT_ID=your_futu_account_id
TRADING_MODE=paper  # paper or live
```

---

## 3. Database Setup

### Option A: Docker (Recommended)

```bash
# Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Wait for services
make wait-for-infra
```

### Option B: Local Installation

```bash
# PostgreSQL with TimescaleDB
CREATE DATABASE aq_trading;
\c aq_trading
CREATE EXTENSION IF NOT EXISTS timescaledb;

# Redis (default config)
redis-server
```

### Run Migrations

```bash
cd backend
alembic upgrade head
```

---

## 4. Start FutuOpenD

FutuOpenD is required for broker connectivity.

### Docker Method

```bash
docker-compose up -d futu-opend

# Access VNC for manual login if needed
# http://localhost:6080
```

### Manual Method

1. Download FutuOpenD from [Futu](https://openapi.futunn.com/)
2. Configure with your credentials
3. Start FutuOpenD daemon
4. Verify listening on port 11111

---

## 5. Start Services

### Backend

```bash
cd backend
uvicorn src.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm run dev
```

### All Services (Docker)

```bash
make start

# This runs:
# 1. PostgreSQL + Redis
# 2. FutuOpenD
# 3. Backend
# 4. Frontend
```

---

## 6. Verify Installation

### Health Check

```bash
curl http://localhost:8000/api/health
# {"status": "ok", "timestamp": "..."}

curl http://localhost:8000/api/health/detailed
# Returns component-level health
```

### Dashboard

Open http://localhost:5173 (Vite dev) or http://localhost:3000 (production)

---

## 7. Run Tests

### Backend

```bash
cd backend
pytest

# With coverage
pytest --cov=src --cov-report=html

# Skip TimescaleDB tests
pytest -m "not timescaledb"
```

### Frontend

```bash
cd frontend
npm run test

# Interactive mode
npm run test:ui
```

---

## 8. Common Commands

### Development

```bash
# Start all services
make start

# Check status
make status

# View logs
make logs

# Stop all
make stop
```

### Database

```bash
# Create migration
cd backend
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

### Code Quality

```bash
# Backend linting
cd backend
ruff check src tests
ruff format src tests

# Frontend type check
cd frontend
npx tsc --noEmit
```

---

## 9. Project Structure Overview

```
aq_trading/
├── backend/               # Python FastAPI backend
│   ├── src/
│   │   ├── api/           # REST API endpoints
│   │   ├── backtest/      # Backtesting engine
│   │   ├── broker/        # Broker integration
│   │   ├── core/          # Core business logic
│   │   ├── db/            # Database layer
│   │   ├── derivatives/   # Options/futures lifecycle (Phase 3)
│   │   ├── greeks/        # Greeks calculations
│   │   ├── health/        # Health monitoring
│   │   ├── models/        # Pydantic models
│   │   ├── risk/          # Risk management
│   │   ├── schemas/       # API schemas
│   │   ├── services/      # Business services
│   │   └── strategies/    # Strategy framework
│   └── tests/             # pytest tests
│
├── agents/                # AI Agent sidecar system (Phase 3)
│   ├── dispatcher.py      # Agent subprocess manager
│   ├── runner.py          # Subprocess entry point
│   ├── permissions.py     # RBAC validation
│   ├── prompts/           # Agent role implementations
│   ├── tools/             # Agent tool scaffolds
│   └── validation/        # Walk-forward validator
│
├── frontend/              # React TypeScript frontend
│   ├── src/
│   │   ├── components/    # UI components
│   │   ├── pages/         # Route pages
│   │   ├── hooks/         # Custom hooks
│   │   ├── api/           # API client
│   │   └── stores/        # State management
│   └── tests/             # vitest tests
│
├── config/                # Configuration files
├── docker/                # Docker files
├── scripts/               # Utility scripts
├── docs/                  # Documentation
└── specs/                 # Feature specifications
```

---

## 10. Key Concepts

### Trading Modes

| Mode | Description |
|------|-------------|
| **paper** | Real market data, simulated execution |
| **live** | Real market data, real execution |
| **backtest** | Historical data, simulated execution |

### Strategy Development

1. Create strategy in `backend/src/strategies/examples/`
2. Implement `Strategy` ABC from `strategies/base.py`
3. Add config in `config/strategies/{name}.yaml`
4. Backtest via API or Dashboard
5. After validation, move to `strategies/live/`

### Signal Flow

```
MarketData → Strategy.on_market_data()
                        ↓
                     Signal
                        ↓
               Risk Manager (validate)
                        ↓
               Order Manager (execute)
                        ↓
              Portfolio Manager (update)
                        ↓
               Strategy.on_fill()
```

---

## 11. Troubleshooting

### FutuOpenD Connection Failed

```bash
# Check if FutuOpenD is running
nc -z localhost 11111

# If not running, check VNC for login issues
open http://localhost:6080
```

### Database Connection Error

```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres
```

### Redis Connection Error

```bash
# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### Frontend Build Error

```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install
```

---

## 12. Next Steps

1. **Configure Risk Limits**: Edit `config/default.yaml` for position limits
2. **Add Market Data**: Set up symbol subscriptions
3. **Create First Strategy**: Copy `strategies/examples/momentum.py` as template
4. **Run Backtest**: Use Dashboard or API to validate strategy
5. **Enable Paper Trading**: Set `TRADING_MODE=paper` and run strategy

---

## Resources

- **STRATEGY.md**: System architecture and design
- **BACKLOG.md**: Implementation progress tracking
- **CLAUDE.md**: AI agent configuration
- **constitution.md**: Development principles

For detailed API documentation, start the backend and visit:
http://localhost:8000/docs (Swagger UI)
