"""Demo answers so the AI visibility screens can be previewed without API keys.

Every row is flagged is_demo and shown with a Demo data badge. For each engine the
screens use demo answers only until that engine has real answers. The answer texts are
invented from templates; they do not come from any AI assistant.
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.analyse import analyse, load_entities
from app.ai.engines import ENGINES, EngineAnswer
from app.ai.plan import PlanConfig, expand, render
from app.ai.runner import store_answer
from app.models import AiAnswer, AiPrompt, AiRun, Organisation, Persona

PRODUCTS = {
    "CeraVe": ("Hydrating Facial Cleanser", ["with ceramides and hyaluronic acid", "fragrance-free and non-comedogenic", "gentle, with ceramides"]),
    "Cetaphil": ("Gentle Skin Cleanser", ["a classic, very mild option", "soap-free and simple"]),
    "La Roche-Posay": ("Toleriane Hydrating Gentle Cleanser", ["with ceramides and niacinamide", "creamy and soothing"]),
    "Vanicream": ("Gentle Facial Cleanser", ["free of common irritants and good value", "a great budget pick"]),
    "Aveeno": ("Calm + Restore Nourishing Oat Cleanser", ["with oat and feverfew, calming for reactive skin", "gentle and soothing"]),
    "Neutrogena": ("Ultra Gentle Daily Cleanser", ["widely available and affordable", "light and easy to find"]),
}
# Each engine leans a little differently, so the demo charts show variation.
ENGINE_BIAS = {
    "openai": ["CeraVe", "La Roche-Posay", "Cetaphil", "Vanicream", "Aveeno", "Neutrogena"],
    "gemini": ["Cetaphil", "CeraVe", "Aveeno", "La Roche-Posay", "Neutrogena", "Vanicream"],
    "perplexity": ["La Roche-Posay", "Vanicream", "CeraVe", "Cetaphil", "Aveeno", "Neutrogena"],
    "anthropic": ["Vanicream", "CeraVe", "La Roche-Posay", "Aveeno", "Cetaphil", "Neutrogena"],
}
CITATIONS = [
    ("https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser", "Hydrating Facial Cleanser | CeraVe"),
    ("https://www.aveeno.com/products/calm-restore-nourishing-oat-cleanser", "Calm + Restore Nourishing Oat Cleanser | Aveeno"),
    ("https://www.reddit.com/r/SkincareAddiction/", "r/SkincareAddiction"),
    ("https://www.byrdie.com/", "Byrdie"),
    ("https://nationaleczema.org/", "National Eczema Association"),
    ("https://www.ulta.com/", "Ulta Beauty"),
    ("https://incidecoder.com/", "INCIDecoder"),
    ("https://www.nykaa.com/", "Nykaa"),
]


def _list_answer(rng: random.Random, engine: str, region: str, persona: str | None) -> str:
    order = list(ENGINE_BIAS[engine])
    if region == "IN":
        order.sort(key=lambda b: 0 if b == "Cetaphil" else 1)
    if persona == "Budget shopper":
        order.sort(key=lambda b: 0 if b in ("Vanicream", "Neutrogena", "CeraVe") else 1)
    if persona == "Eczema-prone adult":
        order.sort(key=lambda b: 0 if b in ("Vanicream", "CeraVe", "Aveeno") else 1)
    for i in range(len(order) - 1):  # a little noise between samples
        if rng.random() < 0.25:
            order[i], order[i + 1] = order[i + 1], order[i]
    picks = order[: rng.choice([3, 4, 4, 5])]
    lines = ["Here are a few gentle options that work well for sensitive skin:", ""]
    for n, brand in enumerate(picks, 1):
        product, phrases = PRODUCTS[brand]
        lines.append(f"{n}. **{brand} {product}**: {rng.choice(phrases)}.")
    lines += ["", "Patch-test anything new and avoid strongly fragranced washes."]
    return "\n".join(lines)


def _answer_text(rng: random.Random, prompt: AiPrompt, engine: str, region: str, persona: str | None) -> str:
    if prompt.intent in ("category", "problem"):
        return _list_answer(rng, engine, region, persona)
    if prompt.intent == "attribute" and "parabens" in prompt.text:
        if rng.random() < 0.3:
            return (
                "Some retailer listings still show an older CeraVe Hydrating Facial Cleanser formula that lists "
                "methylparaben and propylparaben, so check the label. It is fragrance-free."
            )
        return (
            "No. The current CeraVe Hydrating Facial Cleanser doesn't contain parabens. It is fragrance-free and "
            "non-comedogenic, and it carries the National Eczema Association Seal of Acceptance."
        )
    if prompt.intent == "attribute":
        if rng.random() < 0.55:
            return (
                "Yes, Aveeno Calm + Restore Nourishing Oat Cleanser is described as hypoallergenic and fragrance-free, "
                "with oat and feverfew to calm sensitive skin."
            )
        return (
            "Aveeno's own page for the Calm + Restore Nourishing Oat Cleanser lists oat kernel flour and feverfew; "
            "I couldn't find a hypoallergenic claim from the brand itself."
        )
    if prompt.intent == "versus":
        winner = "CeraVe" if engine in ("openai", "anthropic") or rng.random() < 0.4 else "Cetaphil"
        return (
            "Both are gentle. CeraVe Hydrating Facial Cleanser has ceramides and the NEA seal, which helps a damaged "
            "skin barrier. Cetaphil Gentle Skin Cleanser is simpler and very mild. "
            f"For eczema-prone skin I'd lean towards {winner}."
        )
    stores = "Nykaa, Apollo Pharmacy or larger supermarkets" if region == "IN" else "Target, CVS or Walgreens"
    return f"You can usually find Aveeno Calm + Restore Nourishing Oat Cleanser at {stores}, and online from the brand's retailers."


def generate_demo_answers(session: Session, weeks: int = 6, samples: int = 2) -> int:
    """Replace demo answers with a fresh set across all engines, US and India, every persona."""
    session.execute(delete(AiAnswer).where(AiAnswer.is_demo.is_(True)))
    session.execute(delete(AiRun).where(AiRun.is_demo.is_(True)))
    org = session.scalar(select(Organisation).order_by(Organisation.id))
    prompts = session.scalars(select(AiPrompt).where(AiPrompt.organisation_id == org.id)).all() if org else []
    if not org or not prompts:
        session.commit()
        return 0
    personas = session.scalars(select(Persona.id).where(Persona.organisation_id == org.id)).all()
    cfg = PlanConfig(
        prompt_ids=[p.id for p in prompts],
        engines=[{"engine": n, "models": [e.default_models[0]]} for n, e in ENGINES.items()],
        search_modes=[True],
        regions=[{"country": "US", "city": "New York", "languages": ["en"]}, {"country": "IN", "city": "Mumbai", "languages": ["en"]}],
        persona_ids=[None, *personas],
        variants="first",
        samples=samples,
    )
    run = AiRun(organisation_id=org.id, config=cfg.model_dump(), status="done", is_demo=True, analyser="rules", budget_usd=0)
    session.add(run)
    session.flush()
    entities, products = load_entities(session, org.id)
    rng = random.Random(7)
    now = datetime.now(UTC)
    count = 0
    for cell in expand(session, cfg):
        text = _answer_text(rng, cell.prompt, cell.engine.name, cell.region.country, cell.persona.name if cell.persona else None)
        cites = [{"url": u, "title": t} for u, t in rng.sample(CITATIONS, k=rng.randint(2, 4))]
        result = EngineAnswer(
            text=text,
            model_version=f"{cell.model} (demo)",
            citations=cites,
            input_tokens=rng.randint(2500, 5000),
            output_tokens=rng.randint(200, 600),
            latency_ms=rng.randint(1500, 9000),
            search_used=True,
            location_mode=cell.engine.location_mode(True, cell.location),
            searches=1,
        )
        analysis = analyse(session, text, entities, products, {}, "rules")
        asked = now - timedelta(days=rng.randint(0, weeks * 7 - 1), hours=rng.randint(0, 23))
        store_answer(session, run, cell, render(session, cell), result, None, analysis, entities, asked_at=asked, cost=cell.engine.cost(cell.model, result))
        count += 1
    run.planned_calls = run.done_calls = count
    run.finished_at = now
    session.commit()
    return count
