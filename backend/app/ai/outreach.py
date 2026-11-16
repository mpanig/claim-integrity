"""Citation outreach tracker: sites AI answers cite, worked to mention our brands accurately.

Suggestions come from gap sites (cited in answers that recommend a competitor and leave our
brands out). Each tracked site moves to_contact -> contacted -> published (or declined), with an
owner, due date and note. Demo rows show only until the first real row exists.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.coverage import coverage
from app.models import Competitor, Organisation, Outreach, TeamMember

STATUSES = ["to_contact", "contacted", "published", "declined"]
STATUS_LABEL = {"to_contact": "To contact", "contacted": "Contacted", "published": "Published", "declined": "Declined"}


def _squash(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _competitor_sites(session: Session) -> set[str]:
    """Name stems of competitors, to keep their own sites out of outreach (laroche-posay.us, cetaphil.com)."""
    return {_squash(n) for c in session.scalars(select(Competitor)) for n in [c.name, *(c.aliases or [])] if len(_squash(n)) >= 4}


def _targetable(domain: str, page_type: str, rivals: set[str]) -> bool:
    return page_type not in ("retailer", "brand") and not any(r in _squash(domain) for r in rivals)


def _row(o: Outreach, owners: dict[int, str], gaps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    g = gaps.get(o.domain, {})
    return {
        "id": o.id, "domain": o.domain, "page_url": o.page_url, "status": o.status, "owner_id": o.owner_id, "owner": owners.get(o.owner_id),
        "note": o.note, "due_date": o.due_date, "published_url": o.published_url, "gap_citations": o.gap_citations,
        "gap_now": g.get("gap"), "citations_now": g.get("citations"), "created_at": o.created_at, "updated_at": o.updated_at, "is_demo": o.is_demo,
        "overdue": bool(o.due_date and o.status in ("to_contact", "contacted") and o.due_date < datetime.now(UTC).date()),
    }


def tracker(session: Session) -> dict[str, Any]:
    real = session.scalar(select(func.count()).select_from(Outreach).where(Outreach.is_demo.is_(False))) or 0
    rows = list(session.scalars(select(Outreach).where(Outreach.is_demo.is_(real == 0)).order_by(Outreach.updated_at.desc(), Outreach.id.desc())))
    owners = {m.id: m.name for m in session.scalars(select(TeamMember))}
    third = coverage(session)["third_party"]
    gaps = {d["domain"]: d for d in third}
    rivals = _competitor_sites(session)
    tracked = {r.domain for r in rows}
    suggestions = [
        {"domain": d["domain"], "page_type": d["page_type"], "gap": d["gap"], "citations": d["citations"]}
        for d in sorted(third, key=lambda d: (-d["gap"], -d["citations"]))
        if d["gap"] > 0 and d["domain"] not in tracked and _targetable(d["domain"], d["page_type"], rivals)
    ][:12]
    counts = {s: sum(1 for r in rows if r.status == s) for s in STATUSES}
    return {
        "demo": real == 0 and bool(rows),
        "statuses": [{"key": s, "label": STATUS_LABEL[s], "count": counts[s]} for s in STATUSES],
        "rows": [_row(r, owners, gaps) for r in rows],
        "suggestions": suggestions,
        "owners": [{"id": i, "name": n} for i, n in owners.items()],
    }


def add(session: Session, domain: str, *, page_url: str | None = None, owner_id: int | None = None, note: str | None = None, is_demo: bool = False) -> Outreach:
    org = session.scalars(select(Organisation)).first()
    domain = domain.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").split("/")[0]
    gap = next((d["gap"] for d in coverage(session)["third_party"] if d["domain"] == domain), 0)
    o = Outreach(organisation_id=org.id, domain=domain, page_url=page_url, owner_id=owner_id, note=note, gap_citations=gap, is_demo=is_demo)
    session.add(o)
    session.commit()
    return o


def generate_demo_outreach(session: Session) -> int:
    """A few flagged rows across the statuses, on the current top gap sites."""
    session.execute(delete(Outreach).where(Outreach.is_demo.is_(True)))
    session.commit()
    org = session.scalars(select(Organisation)).first()
    if org is None:
        return 0
    rivals = _competitor_sites(session)
    third = sorted((d for d in coverage(session)["third_party"] if d["gap"] > 0 and _targetable(d["domain"], d["page_type"], rivals)), key=lambda d: -d["gap"])[:5]
    team = list(session.scalars(select(TeamMember).order_by(TeamMember.id)))
    plan = [
        ("contacted", "Sent our dermatologist-reviewed facts sheet; waiting on the editor.", 3),
        ("to_contact", "Their eczema round-up recommends Vanicream and Cetaphil only.", 7),
        ("published", "Article updated to include CeraVe with the correct ingredients.", None),
        ("to_contact", "Ask to add Aveeno's oat cleanser to the sensitive-skin list.", -2),
        ("declined", "Editorial policy: no brand-supplied changes.", None),
    ]
    today = datetime.now(UTC).date()
    n = 0
    for d, (status, note, due) in zip(third, plan, strict=False):
        o = Outreach(organisation_id=org.id, domain=d["domain"], status=status, note=note, gap_citations=d["gap"], is_demo=True,
                     owner_id=team[n % len(team)].id if team else None, due_date=today + timedelta(days=due) if due is not None else None,
                     published_url=f"https://{d['domain']}/" if status == "published" else None)
        session.add(o)
        n += 1
    session.commit()
    return n
