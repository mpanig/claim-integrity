from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import ai, alerts, conflicts, recommendations, reports, skus, summary
from app.api.common import DB
from app.config import settings

# TODO(auth): no auth or tenant scoping yet; every route sees every organisation.
app = FastAPI(title="claim-integrity")
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
app.include_router(conflicts.router)
app.include_router(ai.router)
app.include_router(recommendations.router)
app.include_router(alerts.router)
app.include_router(reports.router)
