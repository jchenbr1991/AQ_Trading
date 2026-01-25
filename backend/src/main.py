# backend/src/main.py
from fastapi import FastAPI

from src.api.health import router as health_router
from src.api.orders import router as orders_router
from src.api.portfolio import router as portfolio_mock_router
from src.api.reconciliation import router as reconciliation_router
from src.api.risk import router as risk_router
from src.api.routes import portfolio_router
from src.health.setup import init_health_monitor

app = FastAPI(title="AQ Trading", version="0.1.0")

# Include routers
app.include_router(portfolio_router, prefix="/api")
app.include_router(portfolio_mock_router)  # Phase 1 mock data endpoints
app.include_router(risk_router)
app.include_router(reconciliation_router)
app.include_router(orders_router)
app.include_router(health_router)


@app.on_event("startup")
async def startup_event():
    init_health_monitor()


@app.get("/health")
async def health():
    return {"status": "healthy"}
