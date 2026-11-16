"""Plans, rule-based analysis, truth checks, echoes, rates and insights."""

import httpx
import pytest
from sqlalchemy import select

from app.ai.analyse import analyse, load_entities, page_type, rule_mentions
from app.ai.insights import insights, wilson
from app.ai.plan import PlanConfig, estimate, expand, render
from app.models import AiPrompt, AiRun, Organisation, Persona


@pytest.fixture
def org_id(checked, session):
    return session.scalar(select(Organisation.id))


def plan(session, **over):
    prompts = session.scalars(select(AiPrompt.id).order_by(AiPrompt.id)).all()
    personas = session.scalars(select(Persona.id).order_by(Persona.id)).all()
    cfg = {
        "prompt_ids": prompts[:1],
        "engines": [{"engine": "openai", "models": ["gpt-4.1"]}, {"engine": "perplexity", "models": ["sonar"]}, {"engine": "gemini", "models": ["gemini-2.5-flash"]}],
        "search_modes": [True, False],
        "regions": [{"country": "IN", "city": "Mumbai", "languages": ["en", "hi"]}],
        "persona_ids": [None, personas[0]],
        "variants": "first",
        "samples": 2,
    }
    cfg.update(over)
    return PlanConfig.model_validate(cfg)


def test_plan_expansion_and_rendering(org_id, session):
    cells = expand(session, plan(session))
    # openai 2 search modes + perplexity 1 (always searches) + gemini 2 = 5; x 2 languages x 2 personas x 2 samples
    assert len(cells) == 5 * 2 * 2 * 2
    hindi = [c for c in cells if c.language == "hi"]
    assert hindi[0].template.startswith("संवेदनशील")  # the Hindi variant is used for Hindi

    by = {(c.engine.name, c.search, c.language, c.persona is not None, c.sample): c for c in cells}
    openai_search = render(session, by[("openai", True, "en", True, 1)])
    assert openai_search.startswith("I'm a new parent") and "Mumbai" not in openai_search  # region goes via the API
    gemini = render(session, by[("gemini", True, "en", False, 1)])
    assert gemini.startswith("I'm in Mumbai, India.")  # Gemini has no location option: region in the prompt
    assert "face cleanser" in gemini


def test_language_without_a_variant_asks_for_that_language(org_id, session):
    second = session.scalars(select(AiPrompt.id).order_by(AiPrompt.id)).all()[1]
    cells = expand(session, plan(session, prompt_ids=[second], regions=[{"country": "IN", "languages": ["hi"]}], persona_ids=[None], samples=1))
    assert all(c.template.endswith("Please answer in Hindi.") for c in cells)


def test_estimate_without_keys(org_id, session):
    est = estimate(session, plan(session), {})
    assert est["runnable_calls"] == 0 and est["est_usd"] == 0
    assert est["est_usd_all_engines"] > 0
    assert {e["status"] for e in est["engines"]} == {"key missing"}
    live = estimate(session, plan(session), {"OPENAI_API_KEY": "x"})
    assert live["runnable_calls"] == 2 * 2 * 2 * 2  # openai only


ANSWER = """Here are good options:

1. **Vanicream Gentle Facial Cleanser**: great budget pick.
2. **CeraVe Hydrating Facial Cleanser**: fragrance-free, with ceramides. Older listings show it contains methylparaben.
3. **Aveeno Calm + Restore Nourishing Oat Cleanser**: hypoallergenic and soothing.

Avoid Neutrogena if you react to fragrance."""


def test_rule_analysis_mentions_claims_and_echoes(org_id, session):
    entities, products = load_entities(session, org_id)
    a = analyse(session, ANSWER, entities, products, {}, "rules")
    assert a.analyser == "rules"
    m = {x.entity.name: x for x in a.mentions}
    assert (m["Vanicream"].position, m["CeraVe"].position, m["Aveeno"].position) == (1, 2, 3)
    assert m["CeraVe"].recommended and m["CeraVe"].entity.is_own
    assert not m["Neutrogena"].recommended and m["Neutrogena"].sentiment < 0
    claims = {(c.field, str(c.value)): c for c in a.claims}
    para = claims[("contains", "methylparaben")]
    assert (para.verdict, para.severity) == ("outdated", 6)
    assert para.echo_conflict_ids  # repeats the open Rite Aid ingredient conflict
    assert claims[("contains", "ceramides")].verdict is None  # in the current formula
    assert claims[("free_from", "Fragrance-Free")].verdict == "drift"
    hypo = claims[("claims", "Hypoallergenic")]
    assert hypo.verdict == "risky" and hypo.echo_conflict_ids  # Kenvue Pro shows the same unapproved claim


def test_negated_contains_is_not_a_claim(org_id, session):
    entities, products = load_entities(session, org_id)
    a = analyse(session, "No. The current CeraVe Hydrating Facial Cleanser doesn't contain parabens.", entities, products, {}, "rules")
    assert not [c for c in a.claims if c.field == "contains"]


def test_llm_analyser_output_is_checked_against_the_text(org_id, session, monkeypatch):
    import app.ai.analyse as mod

    entities, products = load_entities(session, org_id)
    fake = {
        "mentions": [{"name": "CeraVe", "position": 1, "recommended": True, "sentiment": 0.8, "quote": "CeraVe Hydrating Facial Cleanser"},
                     {"name": "Cetaphil", "position": 2, "recommended": True, "sentiment": 0.5, "quote": "not in the answer"}],
        "claims": [{"product": "CeraVe Hydrating Facial Cleanser", "field": "claims", "value": "Clinically proven", "quote": "invented quote"}],
    }
    monkeypatch.setattr(mod, "llm_analyse", lambda *a, **k: fake)
    a = analyse(session, "1. CeraVe Hydrating Facial Cleanser is great.", entities, products, {}, "ollama")
    assert a.analyser == "ollama"
    assert [m.entity.name for m in a.mentions] == ["CeraVe"]  # Cetaphil is not in the text
    assert a.claims == []  # quote not in the answer


def test_page_types(org_id, session):
    entities, _ = load_entities(session, org_id)
    assert page_type("https://www.cerave.com/skincare/x", entities) == "brand"
    assert page_type("https://www.reddit.com/r/SkincareAddiction", entities) == "forum"
    assert page_type("https://www.ulta.com/p", entities) == "retailer"
    assert page_type("https://example.org/", entities) == "other"


def test_rule_mentions_without_a_list(org_id, session):
    entities, _ = load_entities(session, org_id)
    ms = rule_mentions("I'd recommend CeraVe. Cetaphil is also fine.", entities)
    assert {m.entity.name: m.position for m in ms} == {"CeraVe": None, "Cetaphil": None}
    assert {m.entity.name: m.recommended for m in ms}["CeraVe"] is True


def test_wilson():
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.237, abs=0.001) and high == pytest.approx(0.763, abs=0.001)


def test_live_answers_replace_demo_per_engine(org_id, session):
    from app.ai.demo import generate_demo_answers
    from app.ai.runner import execute

    generate_demo_answers(session, weeks=1, samples=1, density=0.1)
    before = {e["engine"]: e["mode"] for e in insights(session)["engines"]}
    assert set(before.values()) == {"demo"}

    payload = {
        "model": "gpt-4.1-2025-04-14",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "1. CeraVe Hydrating Facial Cleanser is a great pick.", "annotations": []}]}],
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    run = AiRun(organisation_id=org_id, config=plan(session, samples=1, persona_ids=[None], regions=[{"country": "US", "languages": ["en"]}]).model_dump(), budget_usd=1)
    session.add(run)
    session.commit()
    execute(session, run, env={"OPENAI_API_KEY": "x"}, http=http, sleep=lambda s: None, analyser="rules")
    assert run.status == "done" and run.done_calls == 2  # openai: search on and off
    assert [s["engine"] for s in run.skipped] == ["perplexity", "gemini"]
    after = insights(session)
    modes = {e["engine"]: e["mode"] for e in after["engines"]}
    assert modes["openai"] == "live" and modes["gemini"] == "demo"
    assert next(e for e in after["engines"] if e["engine"] == "openai")["answers"] == 2


def test_budget_stops_the_run(org_id, session):
    from app.ai.runner import execute

    payload = {"model": "m", "output": [{"type": "message", "content": [{"type": "output_text", "text": "ok", "annotations": []}]}], "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    run = AiRun(organisation_id=org_id, config=plan(session).model_dump(), budget_usd=1.0)
    session.add(run)
    session.commit()
    execute(session, run, env={"OPENAI_API_KEY": "x"}, http=http, sleep=lambda s: None, analyser="rules")
    assert run.status == "stopped" and run.done_calls == 1  # first call cost $2 (1M input tokens)


def test_engine_error_is_recorded_and_run_continues(org_id, session):
    from app.ai.runner import execute
    from app.models import AiAnswer

    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")))
    run = AiRun(organisation_id=org_id, config=plan(session, samples=1, persona_ids=[None], regions=[{"country": "US", "languages": ["en"]}]).model_dump(), budget_usd=1)
    session.add(run)
    session.commit()
    execute(session, run, env={"OPENAI_API_KEY": "x"}, http=http, sleep=lambda s: None, analyser="rules")
    assert run.status == "done" and len(run.errors) == 2
    rows = session.scalars(select(AiAnswer).where(AiAnswer.run_id == run.id)).all()
    assert all(r.error and "HTTP 500" in r.error for r in rows)
