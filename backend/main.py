"""Phase 3 FastAPI app — serves GeoJSON + load-flow JSON from PostGIS."""
from __future__ import annotations
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.db.connection import close_pool, init_pool
from backend.routers import analysis, boundaries, grid


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    try:
        yield
    finally:
        await close_pool()


app = FastAPI(
    title='Philippine Power Grid API',
    version='0.4.0',
    lifespan=lifespan,
)

# GZip everything >1 KB. Material wins on the big payloads:
# /api/loadflow/evening_peak (~3 MB JSON → ~600 KB), boundaries (~6 MB → ~1 MB).
app.add_middleware(GZipMiddleware, minimum_size=1024)

# TODO: tighten origins once the Phase 4 frontend has a known host.
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(grid.router)
app.include_router(analysis.router)
app.include_router(boundaries.router)
