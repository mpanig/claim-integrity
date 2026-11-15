"""Team members and roles. TODO(auth): members can't sign in yet; roles don't limit anything."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import DB, get_or_404
from app.models import Brand, Organisation, TeamMember

router = APIRouter()

ROLES = {
    "cmo": "CMO",
    "brand_manager": "Brand manager",
    "ecommerce": "E-commerce",
    "agency": "Agency",
    "regulatory": "Regulatory",
}
Role = Literal["cmo", "brand_manager", "ecommerce", "agency", "regulatory"]

# Which role picks up each recommendation owner type.
OWNER_TYPE_ROLE = {"brand_web": "brand_manager", "ecommerce": "ecommerce", "pr_editorial": "agency", "regulatory": "regulatory"}


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role
    brand_id: int | None = None


class MemberPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role | None = None
    brand_id: int | None = None


def _out(m: TeamMember, brands: dict[int, str]) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "email": m.email,
        "role": m.role,
        "role_label": ROLES[m.role],
        "brand_id": m.brand_id,
        "brand_name": brands.get(m.brand_id) if m.brand_id else None,
    }


def _brands(session) -> dict[int, str]:
    return {b_id: name for b_id, name in session.execute(select(Brand.id, Brand.name))}


@router.get("/team")
def list_team(session: DB) -> dict[str, Any]:
    members = session.scalars(select(TeamMember).order_by(TeamMember.name)).all()
    brands = _brands(session)
    return {"roles": ROLES, "owner_type_role": OWNER_TYPE_ROLE, "members": [_out(m, brands) for m in members]}


@router.post("/team", status_code=201)
def add_member(body: MemberIn, session: DB) -> dict[str, Any]:
    if body.brand_id is not None:
        get_or_404(session, Brand, body.brand_id, "brand")
    org_id = session.scalar(select(Organisation.id).order_by(Organisation.id))  # TODO(auth): caller's org
    if org_id is None:
        raise HTTPException(409, "add a product first")
    exists = session.scalar(select(TeamMember).where(TeamMember.name == body.name.strip()))
    if exists:
        raise HTTPException(409, f"{body.name.strip()} is already on the team")
    m = TeamMember(organisation_id=org_id, name=body.name.strip(), email=body.email, role=body.role, brand_id=body.brand_id)
    session.add(m)
    session.commit()
    return _out(m, _brands(session))


@router.patch("/team/{member_id}")
def update_member(member_id: int, body: MemberPatch, session: DB) -> dict[str, Any]:
    m = get_or_404(session, TeamMember, member_id, "team member")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("brand_id") is not None:
        get_or_404(session, Brand, changes["brand_id"], "brand")
    for key, value in changes.items():
        setattr(m, key, value.strip() if isinstance(value, str) and key == "name" else value)
    session.commit()
    return _out(m, _brands(session))


@router.delete("/team/{member_id}", status_code=204)
def remove_member(member_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, TeamMember, member_id, "team member"))
    session.commit()
    return Response(status_code=204)
