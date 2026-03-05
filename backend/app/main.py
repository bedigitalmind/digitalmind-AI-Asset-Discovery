from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from .core.config import get_settings
from .core.database import engine, Base
from .routers import auth, workspaces, users, files, connectors, taxonomy, detection, reports

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create public schema tables on startup
    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS public'))
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Asset Discovery Tool — API v1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(workspaces.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(files.router, prefix=API_PREFIX)
app.include_router(connectors.router, prefix=API_PREFIX)
app.include_router(taxonomy.router, prefix=API_PREFIX)
app.include_router(detection.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
