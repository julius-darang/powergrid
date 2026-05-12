"""Phase 3 FastAPI app — serves GeoJSON + load-flow JSON from PostGIS."""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db.connection import close_pool, init_pool
from backend.routers import analysis, grid


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title='Philippine Power Grid API',
    version='0.3.0',
    lifespan=lifespan,
)

# TODO: tighten origins once the Phase 4 frontend has a known host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(grid.router)
app.include_router(analysis.router)
