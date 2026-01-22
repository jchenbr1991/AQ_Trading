from fastapi import FastAPI

app = FastAPI(title="AQ Trading", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy"}
