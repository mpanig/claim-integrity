"""Starter prompt library, personas, competitors and aliases for the pilot.

This is configuration, not demo data: real runs use it. Edit it in the app.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AiPrompt, Brand, Competitor, Organisation, Persona, PromptVariant, RunConfig, Sku

COMPETITORS = [
    ("Cetaphil", ["Cetaphil"]),
    ("La Roche-Posay", ["La Roche-Posay", "La Roche Posay", "LRP"]),
    ("Vanicream", ["Vanicream"]),
    ("Neutrogena", ["Neutrogena"]),
    ("Eucerin", ["Eucerin"]),
]
PERSONAS = [
    ("New parent", "I'm a new parent with very little time, and my skin has become dry and sensitive."),
    ("Eczema-prone adult", "I'm an adult with eczema-prone skin that reacts to a lot of products."),
    ("Budget shopper", "I'm on a tight budget and want something good value from a drugstore."),
    ("Dermatologist-informed", "My dermatologist told me to look for a gentle cleanser with ceramides and no fragrance."),
]
BRAND_ALIASES = {"CeraVe": ["CeraVe", "Cera Ve"], "Aveeno": ["Aveeno"]}
SKU_ALIASES = {
    "CeraVe Hydrating Facial Cleanser": ["Hydrating Facial Cleanser", "CeraVe Hydrating Cleanser", "Hydrating Cleanser"],
    "Aveeno Calm + Restore Nourishing Oat Cleanser": [
        "Calm + Restore Nourishing Oat Cleanser", "Nourishing Oat Cleanser", "Calm + Restore Oat Cleanser", "Calm and Restore",
    ],
}


def _prompts(cerave: Sku, aveeno: Sku) -> list[dict]:
    return [
        {
            "intent": "category", "funnel_stage": "awareness", "category": "face cleanser", "sku": None,
            "text": "What's the best {category} for sensitive skin?",
            "variants": [
                ("en", "Which {category} would you recommend for sensitive skin?"),
                ("en", "best {category} for sensitive skin, top picks"),
                ("hi", "संवेदनशील त्वचा के लिए सबसे अच्छा फेस क्लींजर कौन सा है?"),
            ],
        },
        {
            "intent": "problem", "funnel_stage": "awareness", "category": "face cleanser", "sku": None,
            "text": "My face feels dry and tight after washing. What cleanser should I switch to?",
            "variants": [("en", "Which face wash won't strip my dry skin? Give me a few options.")],
        },
        {
            "intent": "attribute", "funnel_stage": "consideration", "sku": cerave,
            "text": "Does {product} contain parabens?",
            "variants": [("en", "Is {product} paraben-free and fragrance-free?")],
        },
        {
            "intent": "attribute", "funnel_stage": "consideration", "sku": aveeno,
            "text": "Is {product} hypoallergenic and fragrance free?",
            "variants": [("en", "What are the key ingredients and claims of {product}?")],
        },
        {
            "intent": "versus", "funnel_stage": "consideration", "sku": cerave, "competitor": "Cetaphil",
            "text": "{brand} vs {competitor}: which gentle cleanser is better for eczema-prone skin?",
            "variants": [("en", "Should I buy {product} or {competitor} Gentle Skin Cleanser?")],
        },
        {
            "intent": "where_to_buy", "funnel_stage": "purchase", "sku": aveeno,
            "text": "Where can I buy {product} near {city}?",
            "variants": [("en", "Which stores in {city} sell {product}?")],
        },
    ]


def seed_library(session: Session, org: Organisation) -> dict[str, int]:
    """Idempotent per organisation: skips anything that already exists."""
    for name, aliases in COMPETITORS:
        if not session.scalar(select(Competitor).where(Competitor.organisation_id == org.id, Competitor.name == name)):
            session.add(Competitor(organisation_id=org.id, name=name, aliases=aliases))
    for name, context in PERSONAS:
        if not session.scalar(select(Persona).where(Persona.organisation_id == org.id, Persona.name == name)):
            session.add(Persona(organisation_id=org.id, name=name, context=context))
    for b in session.scalars(select(Brand).where(Brand.organisation_id == org.id)):
        b.aliases = BRAND_ALIASES.get(b.name, [b.name])
    skus = {s.name: s for s in session.scalars(select(Sku).where(Sku.organisation_id == org.id))}
    for name, aliases in SKU_ALIASES.items():
        if name in skus:
            skus[name].aliases = aliases
    session.flush()

    cerave = skus.get("CeraVe Hydrating Facial Cleanser")
    aveeno = skus.get("Aveeno Calm + Restore Nourishing Oat Cleanser")
    added = 0
    if cerave and aveeno and not session.scalar(select(AiPrompt).where(AiPrompt.organisation_id == org.id)):
        for spec in _prompts(cerave, aveeno):
            sku = spec["sku"]
            p = AiPrompt(
                organisation_id=org.id,
                sku_id=sku.id if sku else None,
                brand_id=sku.brand_id if sku else None,
                text=spec["text"],
                intent=spec["intent"],
                funnel_stage=spec["funnel_stage"],
                category=spec.get("category"),
                competitor=spec.get("competitor"),
            )
            p.variants = [PromptVariant(language=lang, text=t) for lang, t in spec["variants"]]
            session.add(p)
            added += 1
        session.flush()
        personas = session.scalars(select(Persona.id).where(Persona.organisation_id == org.id)).all()
        prompts = session.scalars(select(AiPrompt.id).where(AiPrompt.organisation_id == org.id)).all()
        session.add(
            RunConfig(
                organisation_id=org.id,
                name="Pilot plan: US and India",
                budget_usd=5.0,
                config={
                    "prompt_ids": list(prompts),
                    "engines": [
                        {"engine": "openai", "models": ["gpt-4.1"]},
                        {"engine": "gemini", "models": ["gemini-2.5-flash"]},
                        {"engine": "perplexity", "models": ["sonar"]},
                        {"engine": "anthropic", "models": ["claude-opus-5-5"]},
                    ],
                    "search_modes": [True, False],
                    "regions": [
                        {"country": "US", "city": "New York", "languages": ["en"]},
                        {"country": "IN", "city": "Mumbai", "languages": ["en", "hi"]},
                    ],
                    "persona_ids": [None, *personas],
                    "variants": "first",
                    "samples": 3,
                },
            )
        )
    session.commit()
    return {"prompts": added}
