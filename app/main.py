from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.common.database.session import dispose_database
from app.visits.api.visits import router as visits_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await dispose_database()


app = FastAPI(
    title="Jiris Health API Test",
    description="API for Jiris Health",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.include_router(visits_router, prefix="/api")
