# backend/src/main.py
from fastapi import FastAPI

from src.api.risk import router as risk_router
from src.api.routes import portfolio_router

app = FastAPI(title="AQ Trading", version="0.1.0")

# Include routers
app.include_router(portfolio_router, prefix="/api")
app.include_router(risk_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
