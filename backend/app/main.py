from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Conflict, ConflictStatus, Sku, Verdict
from app.pipeline.run import run_for_sku

# TODO(auth): no auth or tenant scoping yet; every route sees every organisation.
app = FastAPI(title="claim-integrity")
DB = Annotated[Session, Depends(get_session)]


class SkuOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organisation_id: int
    brand_id: int
    gtin: str | None
    name: str
    line: str | None


class ConflictOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku_id: int
    page_id: int
    field: str
    page_value: Any
    truth_value: Any
    verdict: Verdict
    severity: int
    status: ConflictStatus
    detected_at: datetime


def _get_sku(session: Session, sku_id: int) -> Sku:
    sku = session.get(Sku, sku_id)
    if sku is None:
        raise HTTPException(404, "SKU not found")
    return sku


@app.get("/health")
def health(session: DB) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/skus", response_model=list[SkuOut])
def list_skus(session: DB) -> list[Sku]:
    return list(session.scalars(select(Sku).order_by(Sku.id)))


@app.get("/skus/{sku_id}/conflicts", response_model=list[ConflictOut])
def list_conflicts(sku_id: int, session: DB) -> list[Conflict]:
    _get_sku(session, sku_id)
    return list(
        session.scalars(
            select(Conflict)
            .where(Conflict.sku_id == sku_id)
            .order_by(Conflict.severity.desc(), Conflict.id)
        )
    )


@app.post("/skus/{sku_id}/run", response_model=list[ConflictOut])
def run_sku(sku_id: int, session: DB) -> list[Conflict]:
    """Compare stored extractions against the truth; returns the new open conflicts."""
    created = run_for_sku(session, _get_sku(session, sku_id))
    return sorted(created, key=lambda c: (-c.severity, c.id))
