"""Score snapshots, weekly trends and demo history."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import ScoreSnapshot


def test_each_check_writes_a_snapshot(checked, client, session):
    snaps = session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.sku_id == checked["CeraVe"])).all()
    assert len(snaps) == 1
    assert (snaps[0].score, snaps[0].unresolved, snaps[0].is_demo) == (86, 2, False)
    assert snaps[0].by_status["open"] == 2

    client.post(f"/skus/{checked['CeraVe']}/run")
    session.expire_all()
    assert len(session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.sku_id == checked["CeraVe"])).all()) == 2


def test_trends_from_real_snapshots(checked, client):
    t = client.get("/trends", params={"weeks": 4}).json()
    assert t["demo"] is False
    assert len(t["weeks"]) == 4
    this_week = t["weeks"][-1]
    assert (this_week["score"], this_week["unresolved"]) == (40, 12)
    today = datetime.now(UTC).date()  # weeks are bucketed in UTC
    assert this_week["week"] == (today - timedelta(days=today.weekday())).isoformat()
    # Nothing was checked before this week.
    assert all(w["score"] is None for w in t["weeks"][:-1])
    assert {b["name"] for b in t["brands"]} == {"CeraVe", "Aveeno"}


def test_demo_history_is_flagged(checked, client, session):
    from app.services.trends import generate_demo_history

    written = generate_demo_history(session, weeks=12)
    assert written == 24
    t = client.get("/trends", params={"weeks": 12}).json()
    assert t["demo"] is True
    assert all(w["score"] is not None for w in t["weeks"][1:])
    assert all(w["fixed"] >= 0 for w in t["weeks"] if w["fixed"] is not None)
    # The current week still ends on the real score.
    assert t["weeks"][-1]["score"] == 40

    # Running it again replaces the demo rows instead of adding more.
    assert generate_demo_history(session, weeks=12) == 24
    assert len(session.scalars(select(ScoreSnapshot).where(ScoreSnapshot.is_demo.is_(True))).all()) == 24


def test_summary_sources_and_time_to_fix(checked, client):
    s = client.get("/summary").json()
    assert [(x["label"], x["unresolved"]) for x in s["by_source"]] == [
        ("Hannaford", 7),
        ("Kenvue Pro", 3),
        ("Rite Aid", 2),
    ]
    assert s["overall"]["mean_days_to_fix"] is None

    cid = next(c["id"] for c in client.get("/conflicts").json() if c["page_label"] == "Rite Aid")
    for status in ("accepted", "fixed", "verified"):
        client.patch(f"/conflicts/{cid}", json={"status": status})
    assert client.get("/summary").json()["overall"]["mean_days_to_fix"] == 0.0
