# backend/src/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.alerts import router as alerts_router
from src.api.audit import router as audit_router
from src.api.backtest import router as backtest_router
from src.api.health import router as health_router
from src.api.orders import router as orders_router
from src.api.portfolio import router as portfolio_mock_router
from src.api.reconciliation import router as reconciliation_router
from src.api.risk import router as risk_router
from src.api.routes import portfolio_router
from src.api.storage import router as storage_router
from src.health.setup import init_health_monitor


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    init_health_monitor()
    # Note: AlertService is initialized per-request or with background session
    # Use get_alert_service() from src.alerts.setup after initialization
    yield
    # Shutdown


app = FastAPI(title="AQ Trading", version="0.1.0", lifespan=lifespan)

# Include routers
app.include_router(portfolio_router, prefix="/api")
app.include_router(portfolio_mock_router)  # Phase 1 mock data endpoints
app.include_router(risk_router)
app.include_router(reconciliation_router)
app.include_router(orders_router)
app.include_router(health_router)
app.include_router(backtest_router)
app.include_router(storage_router)
app.include_router(alerts_router)
app.include_router(audit_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
