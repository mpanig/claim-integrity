from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import aeo, ai, alerts, audit, conflicts, jobs, recommendations, reports, search, skus, summary, team
from app.api.common import DB
from app.config import settings
from app.db import MAX_OVERFLOW, POOL_SIZE

# Sync endpoints run in a thread pool (40 threads by default). Each holds at most one DB connection, so
# capping the threads at the pool's capacity makes extra requests wait their turn instead of failing.
MAX_CONCURRENT_REQUESTS = POOL_SIZE + MAX_OVERFLOW


@asynccontextmanager
async def lifespan(_app: FastAPI):
    anyio.to_thread.current_default_thread_limiter().total_tokens = MAX_CONCURRENT_REQUESTS
    yield


# TODO(auth): no auth or tenant scoping yet; every route sees every organisation.
app = FastAPI(title="claim-integrity", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(session: DB) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


app.include_router(summary.router)
app.include_router(skus.router)
app.include_router(search.router)  # before conflicts, so /conflicts/bulk isn't read as /conflicts/{id}
app.include_router(conflicts.router)
app.include_router(audit.router)  # before ai: /ai/coverage must not be shadowed
app.include_router(ai.router)
app.include_router(aeo.router)
app.include_router(recommendations.router)
app.include_router(alerts.router)
app.include_router(reports.router)
app.include_router(team.router)
app.include_router(jobs.router)
