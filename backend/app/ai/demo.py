"""Demo answers so the AI visibility screens can be previewed without API keys.

Every row is flagged is_demo and shown with a Demo data badge. For each engine the screens
use demo answers only until that engine has real answers. The answer texts are generated
from templates with a fixed random seed; they do not come from any AI assistant.

Design (latest week): 4 engines x 2 models, web search on/off (Perplexity always on),
US / India (English + Hindi) / UK, no persona + every persona, every prompt with one of its
wordings, `samples` answers per cell. Earlier weeks: a 20% sample with one answer each, so
12 weekly runs show trends without generating ~150k rows.

Built-in patterns (plausible, internally consistent):
  - each engine leans towards different brands; India favours Cetaphil and Neutrogena,
    the UK La Roche-Posay; budget shoppers get Vanicream / Neutrogena, eczema-prone
    shoppers Vanicream / CeraVe / Aveeno, dermatologist-informed shoppers CeraVe
  - CeraVe is mentioned more each week; Aveeno slightly less
  - web search on: more citations, more retailers; search off: no citations and more
    often the old (paraben) CeraVe formula
  - wrong facts that repeat open page conflicts: CeraVe parabens (Rite Aid), "Fragrance
    Free" wording (Rite Aid), Aveeno "hypoallergenic" (Kenvue Pro) and "fragrance-free" (Hannaford)
"""

import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.analyse import analyse, load_entities
from app.ai.engines import ENGINES, EngineAnswer
from app.ai.plan import PlanConfig, expand, render, wordings
from app.ai.runner import store_answer
from app.models import AiAnswer, AiPrompt, AiRun, Organisation, Persona

DEMO_MODELS = {
    "openai": ["gpt-4.1", "gpt-4.1-mini"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro"],
    "perplexity": ["sonar", "sonar-pro"],
    "anthropic": ["claude-opus-5-5", "claude-sonnet-5-5"],
}
REGIONS = [
    {"country": "US", "city": "New York", "languages": ["en"]},
    {"country": "IN", "city": "Mumbai", "languages": ["en", "hi"]},
    {"country": "GB", "city": "London", "languages": ["en"]},
]

PRODUCTS = {
    "CeraVe": "Hydrating Facial Cleanser",
    "Cetaphil": "Gentle Skin Cleanser",
    "La Roche-Posay": "Toleriane Hydrating Gentle Cleanser",
    "Vanicream": "Gentle Facial Cleanser",
    "Aveeno": "Calm + Restore Nourishing Oat Cleanser",
    "Neutrogena": "Ultra Gentle Daily Cleanser",
    "Eucerin": "Gentle Hydrating Cleanser",
}
POSITIVE = {
    "CeraVe": ["with ceramides and hyaluronic acid to support the skin barrier", "gentle and non-comedogenic, a dermatologist favourite", "great value and widely available"],
    "Cetaphil": ["a classic, very mild option", "soap-free and simple, good for reactive skin"],
    "La Roche-Posay": ["with ceramides and niacinamide, creamy and soothing", "well tolerated by very sensitive skin"],
    "Vanicream": ["free of common irritants and great value", "a top budget pick for eczema-prone skin"],
    "Aveeno": ["with oat and feverfew, calming for reactive skin", "gentle and soothing for dry patches"],
    "Neutrogena": ["affordable and easy to find", "light and fine for everyday use"],
    "Eucerin": ["rich and comforting for very dry skin", "a solid pharmacy option"],
}
NEGATIVE = {
    "CeraVe": "some people find the texture a little slippery",
    "Cetaphil": "some users report it doesn't remove makeup well",
    "La Roche-Posay": "it is more expensive than drugstore options",
    "Vanicream": "it can be hard to find outside the US",
    "Aveeno": "a few people report irritation, so patch-test first",
    "Neutrogena": "some formulas can feel drying",
    "Eucerin": "it is pricier for the size",
}
ENGINE_ORDER = {
    "openai": ["CeraVe", "La Roche-Posay", "Cetaphil", "Vanicream", "Aveeno", "Neutrogena", "Eucerin"],
    "gemini": ["Cetaphil", "CeraVe", "Aveeno", "Neutrogena", "La Roche-Posay", "Eucerin", "Vanicream"],
    "perplexity": ["La Roche-Posay", "Vanicream", "CeraVe", "Cetaphil", "Eucerin", "Aveeno", "Neutrogena"],
    "anthropic": ["Vanicream", "CeraVe", "La Roche-Posay", "Aveeno", "Cetaphil", "Neutrogena", "Eucerin"],
}
REGION_BOOST = {"IN": ["Cetaphil", "Neutrogena", "CeraVe"], "GB": ["La Roche-Posay", "CeraVe", "Eucerin"], "US": []}
REGION_SKIP = {"IN": {"Vanicream"}, "GB": {"Vanicream"}, "US": set()}
PERSONA_BOOST = {
    "Budget shopper": ["Vanicream", "Neutrogena", "Cetaphil"],
    "Eczema-prone adult": ["Vanicream", "CeraVe", "Aveeno"],
    "New parent": ["Cetaphil", "Aveeno", "Vanicream"],
    "Dermatologist-informed": ["CeraVe", "La Roche-Posay"],
}

BRAND_SITES = {
    "CeraVe": ("https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser", "Hydrating Facial Cleanser | CeraVe"),
    "Aveeno": ("https://www.aveeno.com/products/calm-restore-nourishing-oat-cleanser", "Calm + Restore Nourishing Oat Cleanser | Aveeno"),
    "Cetaphil": ("https://www.cetaphil.com/us/cleansers/gentle-skin-cleanser", "Gentle Skin Cleanser | Cetaphil"),
    "La Roche-Posay": ("https://www.laroche-posay.us/toleriane-hydrating-gentle-cleanser", "Toleriane Hydrating Gentle Cleanser"),
    "Vanicream": ("https://www.vanicream.com/product/vanicream-gentle-facial-cleanser", "Gentle Facial Cleanser | Vanicream"),
    "Neutrogena": ("https://www.neutrogena.com/", "Neutrogena"),
    "Eucerin": ("https://www.eucerin.com/", "Eucerin"),
}
EDITORIAL = [
    ("https://www.healthline.com/health/beauty-skin-care/best-face-wash-for-sensitive-skin", "Best face washes for sensitive skin | Healthline"),
    ("https://www.byrdie.com/best-cleansers-for-sensitive-skin", "The best cleansers for sensitive skin | Byrdie"),
    ("https://www.allure.com/gallery/best-gentle-cleansers", "Gentle cleansers | Allure"),
    ("https://www.reddit.com/r/SkincareAddiction/", "r/SkincareAddiction"),
    ("https://nationaleczema.org/", "National Eczema Association"),
    ("https://incidecoder.com/", "INCIDecoder"),
]
RETAILERS = {
    "US": [("https://www.amazon.com/", "Amazon.com"), ("https://www.ulta.com/", "Ulta Beauty"), ("https://www.target.com/", "Target")],
    "IN": [("https://www.amazon.in/", "Amazon.in"), ("https://www.nykaa.com/", "Nykaa"), ("https://www.1mg.com/", "Tata 1mg")],
    "GB": [("https://www.boots.com/", "Boots"), ("https://www.superdrug.com/", "Superdrug"), ("https://www.amazon.co.uk/", "Amazon.co.uk")],
}

HI_INTRO = "संवेदनशील त्वचा के लिए ये अच्छे विकल्प हैं:"
HI_OUTRO = "कोई भी नया प्रोडक्ट पहले पैच-टेस्ट करें।"
HI_PHRASES = ["सौम्य और रोज़ इस्तेमाल के लिए अच्छा", "सूखी त्वचा के लिए आरामदायक", "किफ़ायती और आसानी से मिलने वाला"]


def _order(rng: random.Random, engine: str, region: str, persona: str | None, week: int, weeks: int) -> list[str]:
    base = [b for b in ENGINE_ORDER[engine] if b not in REGION_SKIP[region]]
    boost = REGION_BOOST[region] + PERSONA_BOOST.get(persona or "", [])
    order = sorted(base, key=lambda b: boost.index(b) if b in boost else len(boost) + base.index(b))
    progress = week / max(1, weeks - 1)  # 0 = oldest week, 1 = latest
    if "CeraVe" in order and rng.random() < 0.25 + 0.35 * progress:  # CeraVe rises over time
        order.remove("CeraVe")
        order.insert(rng.choice([0, 0, 1]), "CeraVe")
    if "Aveeno" in order and rng.random() < 0.15 * progress:  # Aveeno slips a little
        order.remove("Aveeno")
        order.append("Aveeno")
    for i in range(len(order) - 1):
        if rng.random() < 0.2:
            order[i], order[i + 1] = order[i + 1], order[i]
    return order


def _list_answer(rng: random.Random, picks: list[str], hindi: bool) -> str:
    lines = [HI_INTRO if hindi else "Here are a few gentle options that work well for sensitive skin:", ""]
    for n, brand in enumerate(picks, 1):
        phrase = rng.choice(HI_PHRASES) if hindi else rng.choice(POSITIVE[brand])
        if not hindi and rng.random() < 0.18:
            phrase += f", though {NEGATIVE[brand]}"
        lines.append(f"{n}. **{brand} {PRODUCTS[brand]}**: {phrase}.")
    lines += ["", HI_OUTRO if hindi else "Patch-test anything new and avoid strongly fragranced washes."]
    return "\n".join(lines)


def _answer(rng: random.Random, prompt: AiPrompt, engine: str, region: str, lang: str, persona: str | None, search: bool, week: int, weeks: int) -> tuple[str, list[str]]:
    """Answer text and the brands it leans on (for citations)."""
    hindi = lang == "hi"
    if prompt.intent in ("category", "problem"):
        picks = _order(rng, engine, region, persona, week, weeks)[: rng.choice([3, 4, 4, 5])]
        text = _list_answer(rng, picks, hindi)
        if not hindi and "CeraVe" in picks and rng.random() < 0.25:
            text += "\n\nCeraVe Hydrating Facial Cleanser is fragrance-free and non-comedogenic."
        if not hindi and "Aveeno" in picks and rng.random() < 0.3:
            text += "\n\nAveeno Calm + Restore Nourishing Oat Cleanser is often described as hypoallergenic."
        return text, picks
    if prompt.intent == "attribute" and "parabens" in prompt.text:
        old = rng.random() < (0.45 if not search else 0.18)  # model memory more often has the old formula
        if hindi:
            return ("नहीं, CeraVe Hydrating Facial Cleanser के मौजूदा फ़ॉर्मूले में पैराबेन नहीं हैं।", ["CeraVe"]) if not old else ("कुछ पुराने लेबल पर CeraVe Hydrating Facial Cleanser में methylparaben दिखता है।", ["CeraVe"])
        if old:
            return ("Some listings show an older CeraVe Hydrating Facial Cleanser formula that contains methylparaben and propylparaben, so check the label. It is fragrance-free.", ["CeraVe"])
        tail = " It is fragrance-free" if rng.random() < 0.5 else " It is free of added fragrance"
        return (f"No. The current CeraVe Hydrating Facial Cleanser doesn't contain parabens.{tail}, non-comedogenic, and carries the National Eczema Association Seal of Acceptance.", ["CeraVe"])
    if prompt.intent == "attribute":
        if hindi:
            return ("Aveeno Calm + Restore Nourishing Oat Cleanser में oat और feverfew हैं।", ["Aveeno"])
        if rng.random() < (0.6 if search else 0.45):
            return ("Yes, Aveeno Calm + Restore Nourishing Oat Cleanser is described as hypoallergenic and fragrance-free, with oat and feverfew to calm sensitive skin.", ["Aveeno"])
        return ("Aveeno's own page for the Calm + Restore Nourishing Oat Cleanser lists oat kernel flour and feverfew; I couldn't find a hypoallergenic claim from the brand itself.", ["Aveeno"])
    if prompt.intent == "versus":
        p_cerave = {"openai": 0.75, "anthropic": 0.7, "gemini": 0.45, "perplexity": 0.5}[engine] + (0.1 if persona == "Dermatologist-informed" else 0) - (0.15 if region == "IN" else 0)
        winner = "CeraVe" if rng.random() < p_cerave else "Cetaphil"
        if hindi:
            return (f"दोनों सौम्य हैं। CeraVe Hydrating Facial Cleanser में ceramides हैं; Cetaphil Gentle Skin Cleanser बहुत हल्का है। एक्ज़िमा वाली त्वचा के लिए मैं {winner} चुनूँगा।", ["CeraVe", "Cetaphil"])
        return (
            "Both are gentle. CeraVe Hydrating Facial Cleanser has ceramides and the NEA seal, which helps a damaged skin barrier. "
            f"Cetaphil Gentle Skin Cleanser is simpler and very mild. For eczema-prone skin I'd recommend {winner}.",
            ["CeraVe", "Cetaphil"],
        )
    stores = {"IN": "Nykaa, Apollo Pharmacy or Amazon.in", "GB": "Boots or Superdrug", "US": "Target, CVS or Walgreens"}[region]
    if hindi:
        return (f"Aveeno Calm + Restore Nourishing Oat Cleanser आपको {stores} पर मिल सकता है।", ["Aveeno"])
    return (f"You can usually find Aveeno Calm + Restore Nourishing Oat Cleanser at {stores}, and online from the brand's retailers.", ["Aveeno"])


# Review sites that tend to recommend competitors: cited mostly in answers that leave our brands
# out, so they show up as gap sites (outreach targets) in the demo.
RIVAL_LEANING = [
    ("https://www.verywellhealth.com/best-face-wash-for-eczema", "Best face washes for eczema | Verywell Health"),
    ("https://www.dermstore.com/blog/best-cleansers-for-sensitive-skin/", "Best cleansers for sensitive skin | Dermstore"),
    ("https://www.goodhousekeeping.com/beauty/g31257/best-face-wash/", "Best face washes | Good Housekeeping"),
    ("https://www.cosmopolitan.com/style-beauty/beauty/g2131/best-face-wash/", "Best face washes | Cosmopolitan"),
]
OWN = ("CeraVe", "Aveeno")


def _citations(rng: random.Random, brands: list[str], region: str, search: bool) -> list[dict[str, str]]:
    if not search:
        return []  # without web search, engines don't cite sources
    pool = [BRAND_SITES[b] for b in brands[:3] if b in BRAND_SITES]
    pool += rng.sample(RETAILERS[region], k=rng.randint(1, 2))  # search-on answers lean on retailers
    pool += rng.sample(EDITORIAL, k=rng.randint(1, 3))
    if not any(b in OWN for b in brands):
        pool = rng.sample(RIVAL_LEANING, k=rng.randint(1, 2)) + pool
    elif rng.random() < 0.06:
        pool.append(rng.choice(RIVAL_LEANING))
    lead = pool[:2] if not any(b in OWN for b in brands) else []  # keep rival-leaning sources in view
    rest = pool[len(lead):]
    rng.shuffle(rest)
    return [{"url": u, "title": t} for u, t in (lead + rest)[: rng.randint(3, 6)]]


def generate_demo_answers(session: Session, weeks: int = 12, samples: int = 3, density: float = 1.0, seed: int = 7) -> int:
    """Replace demo answers with a fresh, deterministic set. Never touches non-demo rows."""
    session.execute(delete(AiAnswer).where(AiAnswer.is_demo.is_(True)))
    session.execute(delete(AiRun).where(AiRun.is_demo.is_(True)))
    session.commit()
    org = session.scalar(select(Organisation).order_by(Organisation.id))
    prompts = session.scalars(select(AiPrompt).where(AiPrompt.organisation_id == org.id)).all() if org else []
    if not org or not prompts:
        return 0
    personas = session.scalars(select(Persona.id).where(Persona.organisation_id == org.id)).all()
    cfg = PlanConfig(
        prompt_ids=[p.id for p in prompts],
        engines=[{"engine": n, "models": DEMO_MODELS[n]} for n in ENGINES],
        search_modes=[True, False],
        regions=REGIONS,
        persona_ids=[None, *personas],
        variants="first",
        samples=1,
    )
    base_cells = expand(session, cfg)  # one cell per combination (main wording, one sample)
    entities, products = load_entities(session, org.id)
    rng = random.Random(seed)
    now = datetime.now(UTC)
    count = 0
    for week in range(weeks):  # 0 = oldest
        latest = week == weeks - 1
        week_start = now - timedelta(weeks=weeks - 1 - week, days=now.weekday())
        cells = [c for c in base_cells if rng.random() < (density if latest else 0.2 * density)]
        per_cell = samples if latest else 1
        run = AiRun(organisation_id=org.id, config=cfg.model_dump(), status="done", is_demo=True, analyser="rules", budget_usd=0, started_at=week_start)
        session.add(run)
        session.flush()
        cost = 0.0
        for cell in cells:
            options = wordings(cell.prompt, cell.language, "all")
            for sample in range(1, per_cell + 1):
                cell.template, cell.variant = rng.choice(options)
                cell.sample = sample
                persona = cell.persona.name if cell.persona else None
                text, leaned = _answer(rng, cell.prompt, cell.engine.name, cell.region.country, cell.language, persona, cell.search, week, weeks)
                result = EngineAnswer(
                    text=text,
                    model_version=f"{cell.model} (demo)",
                    citations=_citations(rng, leaned, cell.region.country, cell.search),
                    input_tokens=rng.randint(2500, 6000) if cell.search else rng.randint(150, 400),
                    output_tokens=rng.randint(180, 650),
                    latency_ms=rng.randint(2500, 12000) if cell.search else rng.randint(900, 4000),
                    search_used=cell.search,
                    location_mode=cell.engine.location_mode(cell.search, cell.location),
                    searches=1 if cell.search else 0,
                )
                analysis = analyse(session, text, entities, products, {}, "rules")
                asked = week_start + timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 23))
                c = cell.engine.cost(cell.model, result)
                cost += c
                store_answer(session, run, cell, render(session, cell), result, None, analysis, entities, asked_at=min(asked, now), cost=c)
                count += 1
        run.planned_calls = run.done_calls = len(cells) * per_cell
        run.cost_usd = round(cost, 4)
        run.finished_at = week_start + timedelta(hours=1)
        session.commit()
    return count
