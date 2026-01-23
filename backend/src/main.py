# backend/src/main.py
from fastapi import FastAPI

from src.api.routes import portfolio_router

app = FastAPI(title="AQ Trading", version="0.1.0")

# Include routers
app.include_router(portfolio_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "healthy"}
