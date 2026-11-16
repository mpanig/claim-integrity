"""Prompt discovery: questions shoppers likely ask AI that the library doesn't test yet.

Rules first (always, free): templates per question type, filled from the library's categories,
our SKUs, competitors, personas and the brand-perception attributes. Candidates that
already exist in the library (same words, roughly) are dropped.

Importance is an ESTIMATE, not search volume (no paid keyword API): a base per question
type, raised when the question touches an attribute our positioning wants but AI rarely
gives us, an attribute a competitor owns in AI answers, or a question type where competitors
are recommended instead of us. Reasons are returned with every score.

With an Anthropic key, Claude can suggest more on request (llm=True); each call costs money,
so it never runs by itself.
"""

import hashlib
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.coverage import coverage
from app.ai.engines import engine_env
from app.ai.perception import ATTRIBUTES, perception
from app.models import AiPrompt, Brand, Competitor, Persona, Sku

# "Which is better for ..." phrases (versus questions).
PHRASE = {
    "barrier": "repairing the skin barrier",
    "gentle": "gentle everyday cleansing",
    "sensitive": "sensitive skin",
    "eczema": "eczema-prone skin",
    "derm": "dermatologist approval",
    "hydrating": "dry, dehydrated skin",
    "value": "value for money",
    "natural": "natural, oat-based ingredients",
    "fragrance_free": "avoiding fragrance",
    "available": "being easy to find",
}
# Best-of questions per attribute.
BEST = {
    "barrier": "What is the best {category} for repairing the skin barrier?",
    "gentle": "What is the gentlest {category} for everyday use?",
    "sensitive": "What is the best {category} for sensitive skin?",
    "eczema": "What is the best {category} for eczema-prone skin?",
    "derm": "Which {category} do dermatologists recommend most?",
    "hydrating": "What is the best {category} for dry, dehydrated skin?",
    "value": "What is the best {category} on a budget?",
    "natural": "What is the best natural or oat-based {category}?",
    "fragrance_free": "What is the best fragrance-free {category}?",
    "available": "What is a good {category} I can buy at any pharmacy?",
}
PROBLEM = {
    "eczema": "My skin flares up with eczema. Which {category} won't irritate it?",
    "sensitive": "My face stings after I wash it. Which {category} should I switch to?",
    "hydrating": "My skin feels tight and dry after washing. Which {category} helps?",
    "barrier": "My skin barrier feels damaged. Which {category} helps it recover?",
    "fragrance_free": "Fragrance irritates my skin. Which {category} is truly fragrance-free?",
}
SKU_QUESTIONS = [
    ("Is {sku} fragrance-free?", "fragrance_free"),
    ("Is {sku} safe for eczema-prone skin?", "eczema"),
    ("Does {sku} contain parabens?", None),
    ("Is {sku} non-comedogenic?", None),
    ("Is {sku} good for very dry skin?", "hydrating"),
]
COUNTRIES = {"US": "the US", "IN": "India", "GB": "the UK"}
BASE = {"category": 60, "problem": 55, "versus": 45, "attribute": 35, "where_to_buy": 30}
STAGE = {"category": "awareness", "problem": "awareness", "versus": "consideration", "attribute": "consideration", "where_to_buy": "purchase"}
WORD = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "is", "for", "of", "to", "my", "i", "which", "what", "or", "and", "it", "in", "best", "should", "use", "me"}


def _tokens(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP}


def _similar(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _cid(text: str) -> str:
    return hashlib.sha1(text.lower().encode()).hexdigest()[:12]


def _candidates(session: Session) -> list[dict[str, Any]]:
    prompts = list(session.scalars(select(AiPrompt)))
    categories = sorted({p.category for p in prompts if p.category}) or ["face cleanser"]
    skus = list(session.scalars(select(Sku).options(selectinload(Sku.brand))))
    brands = list(session.scalars(select(Brand)))
    rivals = [c.name for c in session.scalars(select(Competitor).order_by(Competitor.id))]
    personas = list(session.scalars(select(Persona)))
    out: list[dict[str, Any]] = []

    def add(text: str, intent: str, *, category=None, sku_id=None, competitor=None, attribute=None, brand=None):
        out.append({"text": text, "intent": intent, "funnel_stage": STAGE[intent], "category": category, "sku_id": sku_id, "competitor": competitor, "attribute": attribute, "brand": brand})

    for cat in categories:
        for key, tpl in BEST.items():
            add(tpl.format(category=cat), "category", category=cat, attribute=key)
        for key, tpl in PROBLEM.items():
            add(tpl.format(category=cat), "problem", category=cat, attribute=key)
        for p in personas:
            add(f"{p.context.strip()} Which {cat} would you recommend?", "category", category=cat)
    for b in brands:
        for key in (b.positioning or [])[:3]:
            for rival in rivals:
                add(f"{b.name} or {rival}: which is better for {PHRASE.get(key, ATTRIBUTES[key][0].lower())}?", "versus", competitor=rival, attribute=key, brand=b.name)
    for s in skus:
        for tpl, key in SKU_QUESTIONS:
            add(tpl.format(sku=s.name), "attribute", sku_id=s.id, attribute=key, brand=s.brand.name)
        for country in COUNTRIES.values():
            add(f"Where can I buy {s.name} in {country}?", "where_to_buy", sku_id=s.id, brand=s.brand.name)
    return out


def _llm(session: Session, existing: list[str], env: dict[str, str], client: Any = None) -> list[dict[str, Any]]:
    """Up to 15 more shopper questions from Claude, as JSON."""
    import anthropic

    brands = [b.name for b in session.scalars(select(Brand))]
    rivals = [c.name for c in session.scalars(select(Competitor))]
    skus = [s.name for s in session.scalars(select(Sku))]
    schema = {
        "type": "object",
        "properties": {
            "prompts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}, "intent": {"type": "string", "enum": list(BASE)}, "reason": {"type": "string"}},
                    "required": ["text", "intent", "reason"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["prompts"],
        "additionalProperties": False,
    }
    ask = (
        "You help a skincare brand test how AI assistants answer shoppers. Suggest up to 15 realistic questions a "
        "shopper might type into an AI assistant that are NOT already in this list. Mix best-of, problem-led, "
        "brand-vs-brand, product questions and where-to-buy. Write them the way people actually ask. Give a short "
        f"reason for each.\nOur brands: {', '.join(brands)}\nCompetitors: {', '.join(rivals)}\nProducts: {', '.join(skus)}\n"
        "Already tested:\n" + "\n".join(f"- {t}" for t in existing[:80])
    )
    client = client or anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY"))
    resp = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=8000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": ask}],
    )
    if resp.stop_reason == "refusal":
        raise ValueError("declined")
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return [
        {"text": p["text"].strip(), "intent": p["intent"], "funnel_stage": STAGE[p["intent"]], "category": None, "sku_id": None, "competitor": None, "attribute": None, "brand": None, "ai_reason": p["reason"]}
        for p in data.get("prompts", [])
        if p.get("intent") in BASE and len(p.get("text", "")) >= 5
    ]


def discover(session: Session, *, llm: bool = False, env: dict[str, str] | None = None, anthropic_client: Any = None) -> dict[str, Any]:
    env = engine_env() if env is None else env
    prompts = list(session.scalars(select(AiPrompt).options(selectinload(AiPrompt.variants))))
    library = [(p.id, _tokens(t)) for p in prompts for t in [p.text, *(v.text for v in p.variants)]]

    cands = [{**c, "source": "rules"} for c in _candidates(session)]
    llm_status = "available" if env.get("ANTHROPIC_API_KEY") else "no key"
    if llm and env.get("ANTHROPIC_API_KEY"):
        try:
            cands += [{**c, "source": "claude"} for c in _llm(session, [p.text for p in prompts], env, anthropic_client)]
            llm_status = "used"
        except Exception as e:  # noqa: BLE001 - shown to the user, rules still work
            llm_status = f"error: {type(e).__name__}"

    # Signals for the importance estimate.
    per = perception(session)
    leaders = per["leaders"]
    own = {b["name"] for b in per["brands"] if b["is_own"]}
    missing: dict[str, list[str]] = {}
    for b in per["brands"]:
        for g in b["gaps"]:
            if g["kind"] == "missing":
                missing.setdefault(g["attribute"], []).append(b["name"])
    losing = {u["use_case"].split(":")[0] for u in coverage(session)["use_cases"] if u["gap"] > 0.1}
    intent_label = {"category": "Best-of", "problem": "Problem-led", "attribute": "Product question", "versus": "Brand vs brand", "where_to_buy": "Where to buy"}

    seen: set[str] = set()
    result, covered = [], 0
    for c in cands:
        toks = _tokens(c["text"])
        key = " ".join(sorted(toks))
        if key in seen:
            continue
        seen.add(key)
        match = max(library, key=lambda lt: _similar(toks, lt[1]), default=None)
        if match and _similar(toks, match[1]) >= 0.6:
            covered += 1
            continue
        score, reasons = BASE[c["intent"]], [f"{intent_label[c['intent']]} questions: base {BASE[c['intent']]}"]
        a = c.get("attribute")
        # A question about one brand only counts that brand's gap; open questions count any of ours.
        gap_brands = [n for n in missing.get(a, []) if not c.get("brand") or n == c["brand"]] if a else []
        if gap_brands:
            score += 20
            reasons.append(f"Positioning gap: AI rarely calls {' or '.join(gap_brands)} “{ATTRIBUTES[a][0].lower()}”")
        if a and leaders.get(a) and leaders[a] not in own:
            score += 15
            reasons.append(f"{leaders[a]} owns “{ATTRIBUTES[a][0].lower()}” in AI answers")
        if intent_label[c["intent"]] in losing:
            score += 10
            reasons.append(f"Competitors win {intent_label[c['intent']].lower()} questions today")
        if c.get("ai_reason"):
            reasons.append(f"Claude: {c['ai_reason']}")
        result.append({**c, "id": _cid(c["text"]), "importance": min(100, score), "reasons": reasons})
    result.sort(key=lambda c: (-c["importance"], c["intent"], c["text"]))
    return {"candidates": result, "already_covered": covered, "llm": llm_status, "importance_note": "Estimated from your AI answers and positioning, not from search volume."}
