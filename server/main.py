from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.metrics import router as metrics_router
from routers.signal_webhook import router as signal_router

app = FastAPI(title="WHOOP Health Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router)
app.include_router(signal_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
