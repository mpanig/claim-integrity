"""Turn a snapshot into structured fields for one SKU.

Extracted fields have the shape {field: {"value": ..., "quote": "<text from the page>"}}.
The quote is the evidence a reviewer checks against the snapshot.
"""

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Extraction, Sku, Snapshot


class ExtractedField(BaseModel):
    value: Any
    quote: str | None = None


class Extractor(Protocol):
    def extract(self, snapshot: Snapshot, sku: Sku) -> dict[str, dict[str, Any]]: ...


class ManualExtractor:
    """Reads hand-written fields from a JSON fixture: {"<page url>": {field: {value, quote}}}."""

    def __init__(self, by_url: dict[str, dict[str, Any]]):
        self._by_url = by_url

    @classmethod
    def from_file(cls, path: Path) -> "ManualExtractor":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def extract(self, snapshot: Snapshot, sku: Sku) -> dict[str, dict[str, Any]]:
        raw = self._by_url.get(snapshot.page.url)
        if raw is None:
            raise KeyError(f"no manual extraction for {snapshot.page.url}")
        return {name: ExtractedField.model_validate(f).model_dump() for name, f in raw.items()}


# TODO(phase 2): LLMExtractor implementing Extractor, once API keys are available.


def save_extraction(session: Session, extractor: Extractor, snapshot: Snapshot, sku: Sku) -> Extraction:
    extraction = Extraction(
        organisation_id=sku.organisation_id,
        snapshot_id=snapshot.id,
        sku_id=sku.id,
        fields=extractor.extract(snapshot, sku),
    )
    session.add(extraction)
    session.flush()
    return extraction
