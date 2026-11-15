"""Fetch a page and store a snapshot, skipping it when the content has not changed."""

import hashlib

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Page, Snapshot

USER_AGENT = "claim-integrity/0.1"


def content_hash(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def store_snapshot(session: Session, page: Page, html: str) -> Snapshot | None:
    """Add a snapshot for `page`, or return None if the latest one has the same hash."""
    digest = content_hash(html)
    latest = session.scalar(
        select(Snapshot.content_hash)
        .where(Snapshot.page_id == page.id)
        .order_by(Snapshot.fetched_at.desc(), Snapshot.id.desc())
        .limit(1)
    )
    if latest == digest:
        return None
    snapshot = Snapshot(
        organisation_id=page.organisation_id, page_id=page.id, content_hash=digest, html=html
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def fetch_page(session: Session, page: Page, client: httpx.Client | None = None) -> Snapshot | None:
    """GET page.url and store a snapshot. Raises httpx.HTTPError on network/HTTP errors."""
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        response = client.get(page.url)
        response.raise_for_status()
    finally:
        if owns_client:
            client.close()
    return store_snapshot(session, page, response.text)
