import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import cs
from .api_admin import router as admin_router
from .api_shop import router as shop_router
from .config import settings
from .copilot.retrieve import get_retriever
from .db import Base, SessionLocal, engine
from .seed import ensure_seeded


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    if os.getenv("SEED_DEMO", "1") == "1":
        with SessionLocal() as db:
            ensure_seeded(db)
    yield


app = FastAPI(title="CatBooks API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(shop_router)
app.include_router(admin_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm_provider": cs.get_llm().name, "kb_chunks": len(get_retriever().chunks),
            "demo_tools": settings.demo_tools}
