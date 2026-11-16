"""Execute a test plan: ask each engine, store the raw answer with every factor, analyse it.

Engines without a key are skipped and listed on the run. The run stops when the
budget (USD) is reached. One failing call is recorded and the run continues.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.ai.analyse import Analysis, analyse, load_entities, page_type, pick_analyser
from app.ai.engines import ENGINES, EngineAnswer, EngineError, engine_env
from app.ai.plan import Cell, PlanConfig, expand, render
from app.models import AiAnswer, AiRun, AnswerCitation, AnswerClaim, AnswerMention

PAUSE_BETWEEN_CALLS = 1.0  # seconds, per call, to stay well inside provider rate limits


def store_answer(
    session: Session,
    run: AiRun,
    cell: Cell,
    prompt_text: str,
    result: EngineAnswer | None,
    error: str | None,
    analysis: Analysis | None,
    entities: list[Any],
    *,
    asked_at: datetime | None = None,
    cost: float | None = None,
) -> AiAnswer:
    sku_id = cell.prompt.sku_id
    row = AiAnswer(
        organisation_id=run.organisation_id,
        prompt_id=cell.prompt.id,
        sku_id=sku_id,
        assistant=f"{cell.engine.label} {cell.model}",
        answer=result.text if result else "",
        run_id=run.id,
        variant_id=cell.variant.id if cell.variant else None,
        persona_id=cell.persona.id if cell.persona else None,
        prompt_text=prompt_text,
        engine=cell.engine.name,
        model_requested=cell.model,
        model_version=result.model_version if result else None,
        search_enabled=cell.search,
        region=cell.region.country.upper(),
        city=cell.region.city,
        language=cell.language,
        location_mode=result.location_mode if result else cell.engine.location_mode(cell.search, cell.location),
        sample_index=cell.sample,
        temperature=None,  # provider default
        latency_ms=result.latency_ms if result else None,
        input_tokens=result.input_tokens if result else None,
        output_tokens=result.output_tokens if result else None,
        cost_usd=cost,
        analyser=analysis.analyser if analysis else None,
        error=error,
        is_demo=run.is_demo,
    )
    if asked_at:
        row.asked_at = asked_at
    session.add(row)
    session.flush()
    if analysis:
        for m in analysis.mentions:
            session.add(
                AnswerMention(
                    answer_id=row.id, name=m.entity.name, brand_id=m.entity.brand_id, competitor_id=m.entity.competitor_id,
                    is_own=m.entity.is_own, position=m.position, recommended=m.recommended, sentiment=m.sentiment, quote=m.quote,
                )
            )
        facts: dict[str, list[Any]] = {}
        for c in analysis.claims:
            session.add(
                AnswerClaim(
                    answer_id=row.id, sku_id=c.sku_id, field=c.field, value=c.value, quote=c.quote,
                    verdict=c.verdict, severity=c.severity, echo_conflict_ids=c.echo_conflict_ids,
                )
            )
            if c.sku_id == sku_id:
                facts.setdefault(c.field, []).append(c.value)
        row.stated_facts = facts
        row.mentioned_brands = [m.entity.name for m in analysis.mentions]
    for cite in (result.citations if result else []):
        from urllib.parse import urlsplit

        domain = (urlsplit(cite["url"]).hostname or "").removeprefix("www.")
        session.add(AnswerCitation(answer_id=row.id, url=cite["url"][:2000], domain=domain[:255], title=cite.get("title") or None, page_type=page_type(cite["url"], entities)))
    return row


def execute(
    session: Session,
    run: AiRun,
    *,
    env: dict[str, str] | None = None,
    http: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
    analyser: str | None = None,
) -> AiRun:
    env = engine_env() if env is None else env
    own_http = http is None
    http = http or httpx.Client()
    try:
        cfg = PlanConfig.model_validate(run.config)
        cells = expand(session, cfg)
        live = {name for name, e in ENGINES.items() if e.status(env) == "live"}
        run.skipped = [
            {"engine": name, "reason": f"{ENGINES[name].env_key} not set", "calls": n}
            for name, n in _count_by_engine(cells).items()
            if name not in live
        ]
        cells = [c for c in cells if c.engine.name in live]
        run.planned_calls = len(cells)
        run.analyser = analyser or pick_analyser(env, http)
        entities, products = load_entities(session, run.organisation_id)
        session.commit()

        for cell in cells:
            if run.cost_usd >= run.budget_usd:
                run.status = "stopped"
                run.errors = [*run.errors, {"error": f"budget of ${run.budget_usd:.2f} reached"}]
                break
            prompt_text = render(session, cell)
            result, error, analysis, cost = None, None, None, None
            try:
                result = cell.engine.ask(prompt_text, model=cell.model, search=cell.search, loc=cell.location, env=env, http=http)
                cost = cell.engine.cost(cell.model, result)
            except EngineError as e:
                error = str(e)
                run.errors = [*run.errors, {"engine": cell.engine.name, "error": error[:300]}]
            if result and result.text:
                analysis = analyse(session, result.text, entities, products, env, run.analyser, http=http)
            store_answer(session, run, cell, prompt_text, result, error, analysis, entities, cost=cost)
            run.done_calls += 1
            run.cost_usd = round(run.cost_usd + (cost or 0), 6)
            session.commit()
            sleep(PAUSE_BETWEEN_CALLS)
        if run.status == "running":
            run.status = "done"
    except Exception as e:
        session.rollback()
        run.status = "failed"
        run.errors = [*run.errors, {"error": f"{type(e).__name__}: {e}"[:300]}]
    finally:
        if own_http:
            http.close()
    run.finished_at = datetime.now(UTC)
    session.commit()
    if run.done_calls:
        try:  # AEO alerts compare this week's answers with last week's
            from app.ai.aeo_alerts import evaluate

            evaluate(session, env=env)
        except Exception:  # noqa: BLE001 - alerts must never fail a run
            session.rollback()
    return run


def _count_by_engine(cells: list[Cell]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cells:
        out[c.engine.name] = out.get(c.engine.name, 0) + 1
    return out
