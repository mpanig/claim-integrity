from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import DB, get_or_404
from app.models import AiPrompt, Organisation, Sku
from app.services.ai_visibility import overview

router = APIRouter()


class PromptIn(BaseModel):
    text: str = Field(min_length=5, max_length=500)
    sku_id: int | None = None


@router.get("/ai-visibility")
def ai_visibility(session: DB, brand_id: int | None = None) -> dict[str, Any]:
    return overview(session, brand_id)


@router.post("/ai-visibility/prompts", status_code=201)
def add_prompt(body: PromptIn, session: DB) -> dict[str, Any]:
    """Save a question to track. It is asked once assistants are connected (TODO)."""
    sku = get_or_404(session, Sku, body.sku_id, "SKU") if body.sku_id is not None else None
    org_id = sku.organisation_id if sku else session.scalar(select(Organisation.id).order_by(Organisation.id))
    if org_id is None:
        raise HTTPException(409, "add a product first")
    p = AiPrompt(
        organisation_id=org_id,
        sku_id=sku.id if sku else None,
        brand_id=sku.brand_id if sku else None,
        text=body.text.strip(),
    )
    session.add(p)
    session.commit()
    return {"id": p.id, "text": p.text, "sku_id": p.sku_id}


@router.delete("/ai-visibility/prompts/{prompt_id}", status_code=204)
def delete_prompt(prompt_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, AiPrompt, prompt_id, "prompt"))
    session.commit()
    return Response(status_code=204)
