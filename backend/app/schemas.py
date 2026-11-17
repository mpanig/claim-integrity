from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import ConflictStatus, Verdict


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class SkuOut(BaseModel):
    id: int
    organisation_id: int
    brand_id: int
    brand_name: str
    gtin: str | None
    name: str
    line: str | None
    last_checked_at: datetime | None
    score: int | None  # consistency (100 = no drift); kept for older clients, use drift_score
    drift_score: int | None = None  # 0 = no drift, higher = pages drift further from the truth
    unresolved: int
    by_verdict: dict[str, int]
    pages: int
    truth_status: str = "approved"  # approved | inferred (no truth sheet, unverified) | none
    inferred_method: str | None = None  # majority | claude


class SkuIn(BaseModel):
    brand_id: int | None = None
    brand_name: str | None = None  # creates the brand if it does not exist
    name: str = Field(min_length=1, max_length=300)
    gtin: str | None = Field(default=None, max_length=14)
    line: str | None = None
    claims: dict[str, Any] = {}
    evidence_url: str | None = None


class SkuPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    gtin: str | None = Field(default=None, max_length=14)
    line: str | None = None


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: str
    value: Any
    evidence_url: str | None
    approved_by: str | None
    created_at: datetime


class ClaimIn(BaseModel):
    value: Any
    evidence_url: str | None = None


class ConflictOut(BaseModel):
    id: int
    sku_id: int
    sku_name: str
    brand_id: int
    brand_name: str
    page_id: int
    page_url: str
    page_label: str
    source_type: str
    field: str
    page_value: Any
    truth_value: Any
    verdict: Verdict
    severity: int
    status: ConflictStatus
    owner: str | None
    truth_source: str = "approved"
    due_date: date | None
    dismiss_reason: str | None
    detected_at: datetime
    status_changed_at: datetime | None


class ConflictDetail(ConflictOut):
    quote: str | None
    truth_evidence_url: str | None
    page_fetched_at: datetime | None
    allowed_transitions: list[ConflictStatus]


class ConflictPatch(BaseModel):
    """Only the fields that are sent are changed; send owner/due_date as null to clear them."""

    status: ConflictStatus | None = None
    reason: str | None = None
    owner: str | None = None
    due_date: date | None = None


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class EventOut(BaseModel):
    id: int
    sku_id: int
    sku_name: str
    conflict_id: int | None
    actor: str
    action: str
    detail: dict[str, Any]
    at: datetime


class RunOut(BaseModel):
    new: int
    reopened: int
    resolved: int
    unresolved: int
    score: int | None
    drift_score: int | None = None
    truth_status: str = "approved"
