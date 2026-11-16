"""Fetch a page through an ordered fallback chain:

  1. direct      plain HTTP GET
  2. rendered    headless browser, if Playwright and a browser are installed
  3. jina_reader Jina Reader turns JS-heavy pages into text (keyless at a strict rate)

robots.txt is checked once, for the page itself, before any step; a disallowed
page is not fetched by any route. Fetched content is data, never instructions.
"""

import httpx

from app.collector.base import Context
from app.collector.extract import visible_text
from app.collector.http import Blocked, BudgetExceeded, Fetched

MIN_TEXT = 400  # characters of visible text before a page counts as fetched
JINA_HOST = "r.jina.ai"


def _text_len(f: Fetched) -> int:
    if "html" in f.content_type:
        from bs4 import BeautifulSoup

        return len(visible_text(BeautifulSoup(f.text, "html.parser")))
    return len(f.text.strip())


def _useful(f: Fetched | None) -> bool:
    return f is not None and f.status == 200 and _text_len(f) >= MIN_TEXT


def render_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _rendered(ctx: Context, url: str) -> Fetched:
    from playwright.sync_api import sync_playwright

    ctx.http.spend()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=ctx.http.user_agent)
            res = page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            return Fetched(url, page.url, res.status if res else 0, html, "text/html", via="rendered")
        finally:
            browser.close()


def _jina(ctx: Context, url: str) -> Fetched:
    headers = {"Accept": "text/plain", "X-Return-Format": "text"}
    key = ctx.env.get("JINA_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    res = ctx.http.api("GET", f"https://{JINA_HOST}/{url}", headers=headers)
    return Fetched(url, url, res.status_code, res.text, "text/plain", via="jina_reader")


def fetch_page(ctx: Context, url: str) -> Fetched | None:
    """Best result from the chain, or None. Raises Blocked if robots.txt disallows the page."""
    if not ctx.http.robots_allows(url):
        raise Blocked(f"robots.txt disallows {url}")
    attempts: list[dict] = []
    best: Fetched | None = None

    steps = [("direct", lambda: ctx.http.get_html(url))]
    if "rendered" in ctx.enabled and render_available():
        steps.append(("rendered", lambda: _rendered(ctx, url)))
    elif "rendered" in ctx.enabled:
        attempts.append({"via": "rendered", "skipped": "Playwright is not installed"})
    if "jina_reader" in ctx.enabled:
        steps.append(("jina_reader", lambda: _jina(ctx, url)))

    for via, run in steps:
        try:
            f = run()
        except BudgetExceeded:
            raise
        except (httpx.HTTPError, Blocked, Exception) as e:  # one failing route must not stop the chain
            attempts.append({"via": via, "error": f"{type(e).__name__}: {e}"[:200]})
            continue
        attempts.append({"via": via, "status": f.status, "chars": _text_len(f)})
        if best is None or (f.status == 200 and best.status != 200):
            best = f
        if _useful(f):
            best = f
            break
    ctx.note("fetch", url=url, attempts=attempts, used=best.via if _useful(best) else None)
    return best if _useful(best) else None
