"""Connectors. Each finds candidates for a brand/product and knows how to read them.

Keyed connectors are skipped with a reason when their key is missing.
API responses and pages are data; nothing in them is followed as an instruction.
"""

import re
from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlsplit

import defusedxml.ElementTree as SafeET

from app.collector.base import BrandInfo, Candidate, Connector, Context, Parsed, SkuInfo
from app.collector.http import Blocked, Fetched, host_of
from app.collector.relevance import tokens

RETAILER_HOSTS = (
    "target.com", "walgreens.com", "cvs.com", "ulta.com", "sephora.com", "hannaford.com", "riteaid.com",
    "kroger.com", "boots.com", "superdrug.com", "dermstore.com", "costco.com", "samsclub.com", "heb.com",
    "meijer.com", "giantfood.com", "stopandshop.com", "shoppersdrugmart.ca", "londondrugs.com",
)


def guess_source_type(url: str, brand: BrandInfo) -> str:
    host = host_of(url)
    if brand.site_url and host_of(brand.site_url).removeprefix("www.") in host:
        return "brand"
    if any(host.endswith(h) for h in RETAILER_HOSTS):
        return "retailer"
    if "reddit.com" in host:
        return "social"
    if "youtube.com" in host or "youtu.be" in host:
        return "video"
    return "article"


def product_words(brand: BrandInfo, sku: SkuInfo | None) -> str:
    if sku is None:
        return brand.name
    name = sku.name
    return name if brand.name.lower() in name.lower() else f"{brand.name} {name}"


def default_queries(brand: BrandInfo, sku: SkuInfo | None) -> list[str]:
    """Fixed query templates, used when no planner (Claude) is available."""
    if sku is None:
        return [brand.name]
    product = product_words(brand, sku)
    noun = sku.name.split()[-1].lower()
    return [f"{product} ingredients", product, f"best {noun} for sensitive skin"]


# --------------------------------------------------------------------------- brand site


class BrandSite(Connector):
    name = "brand_site"
    label = "Brand website"
    description = "Reads the brand site's robots.txt and sitemap to find the product's own page."
    source_type = "brand"
    kind = "page"
    weight = 1.0
    max_sitemaps = 6
    max_urls = 20_000

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        if sku is None:
            return []
        if not brand.site_url:
            ctx.note("brand_site", skipped="no brand site URL on the truth sheet")
            return []
        root = f"{urlsplit(brand.site_url).scheme}://{urlsplit(brand.site_url).netloc}"
        key = f"sitemap_urls:{root}"
        if key not in ctx.cache:
            ctx.cache[key] = self._sitemap_urls(ctx, root)
        return match_product_urls(ctx.cache[key], brand, sku)

    def _sitemap_urls(self, ctx: Context, root: str) -> list[str]:
        ctx.http.set_interval(host_of(root), self.interval)
        sitemaps = ctx.http.sitemaps_for(root) or [urljoin(root, "/sitemap.xml")]
        urls: list[str] = []
        seen, queue = set(), list(sitemaps)
        while queue and len(seen) < self.max_sitemaps and len(urls) < self.max_urls:
            sm = queue.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            try:
                res = ctx.http.get_html(sm)
            except Blocked as e:
                ctx.note("brand_site", sitemap=sm, skipped=str(e))
                continue
            if res.status != 200:
                ctx.note("brand_site", sitemap=sm, status=res.status)
                continue
            child_maps, page_urls = parse_sitemap(res.text)
            # Prefer product sitemaps when the index lists several.
            queue.extend(sorted(child_maps, key=lambda u: "product" not in u.lower()))
            urls.extend(page_urls)
        ctx.note("brand_site", sitemaps_read=len(seen), urls=len(urls))
        return urls


def parse_sitemap(xml: str) -> tuple[list[str], list[str]]:
    """(child sitemap URLs, page URLs). defusedxml guards against XML bombs."""
    # Parse the already-decoded text: some sites declare an encoding (e.g. utf-16) that
    # doesn't match what they actually send, so the declaration is dropped.
    text = xml.decode("utf-8", "replace") if isinstance(xml, bytes) else xml
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        root = SafeET.fromstring(text)
    except Exception:  # not XML (HTML error page etc.)
        return [], []
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"
    locs = [el.text.strip() for el in root.iter(f"{ns}loc") if el.text]
    if root.tag.endswith("sitemapindex"):
        return locs, []
    return [], locs


def match_product_urls(urls: list[str], brand: BrandInfo, sku: SkuInfo, limit: int = 3) -> list[Candidate]:
    want = tokens(sku.name) - tokens(brand.name)
    scored = []
    for u in urls:
        slug = tokens(urlsplit(u).path)
        if not want:
            continue
        hit = len(want & slug) / len(want)
        extra = len(slug - want - {"product", "products", "skincare", "en", "us", "html", "p"})
        if hit >= 0.6:
            scored.append((hit, -extra, u))
    scored.sort(reverse=True)
    return [
        Candidate(
            url=u,
            connector="brand_site",
            source_type="brand",
            kind="page",
            title=urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
            why=f"brand sitemap URL matches {round(hit * 100)}% of the product name",
        )
        for hit, _, u in scored[:limit]
    ]


# --------------------------------------------------------------------------- Open Beauty Facts

OBF = "https://world.openbeautyfacts.org"
OBF_FIELDS = "code,product_name,brands,ingredients_text,ingredients_text_en,labels,image_front_url"


class OpenBeautyFacts(Connector):
    name = "open_beauty_facts"
    label = "Open Beauty Facts"
    description = "Open, crowd-sourced product database: ingredients and labels by barcode or name."
    source_type = "database"
    kind = "page"
    interval = 6.5  # their search API allows about 10 requests a minute
    weight = 0.5  # crowd-sourced, so it counts less than a retailer page
    hosts = ("world.openbeautyfacts.org",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        if sku is None:
            return []
        products: list[dict[str, Any]] = []
        if sku.gtin:
            res = ctx.http.api("GET", f"{OBF}/api/v2/product/{quote(sku.gtin)}.json", params={"fields": OBF_FIELDS})
            if res.status_code == 200 and res.json().get("status") == 1:
                products.append(res.json()["product"])
        if not products:
            res = ctx.http.api(
                "GET",
                f"{OBF}/cgi/search.pl",
                params={
                    "search_terms": product_words(brand, sku),
                    "search_simple": 1,
                    "action": "process",
                    "json": 1,
                    "page_size": 10,
                    "fields": OBF_FIELDS,
                },
            )
            if res.status_code == 200:
                products = res.json().get("products", [])
            else:
                ctx.note("open_beauty_facts", status=res.status_code)
        return [self._candidate(p) for p in products if p.get("code")]

    def _candidate(self, p: dict[str, Any]) -> Candidate:
        return Candidate(
            url=f"{OBF}/product/{p['code']}",
            connector=self.name,
            source_type=self.source_type,
            kind="page",
            title=" ".join(x for x in (p.get("brands"), p.get("product_name")) if x),
            why="Open Beauty Facts record",
            gtin=str(p["code"]),
            data=p,
            parsed=parse_obf(p),
        )

    def fetch(self, ctx: Context, candidate: Candidate) -> Fetched | None:
        import json

        # Already fetched through the API during discovery; store that JSON as the snapshot.
        return Fetched(candidate.url, candidate.url, 200, json.dumps(candidate.data, sort_keys=True), "application/json", via="api")

    def parse(self, fetched: Fetched, candidate: Candidate) -> Parsed | None:
        return candidate.parsed


def parse_obf(p: dict[str, Any]) -> Parsed:
    from app.collector.extract import rules_from_text

    parsed = Parsed(method="open_beauty_facts", gtin=str(p.get("code") or "") or None)
    brand, name = (p.get("brands") or "").split(",")[0].strip(), (p.get("product_name") or "").strip()
    if name:
        full = name if brand.lower() in name.lower() else f"{brand} {name}".strip()
        parsed.name = full
        parsed.fields["name"] = {"value": full, "quote": f"Open Beauty Facts: product_name = {name}; brands = {brand}"}
    raw = (p.get("ingredients_text_en") or p.get("ingredients_text") or "").strip()
    if raw:
        body = re.sub(r"^\s*ingredients?\s*[:\-]\s*", "", raw, flags=re.I)
        items = [i.strip(" .;*") for i in body.split(",") if i.strip(" .;*")]
        if len(items) >= 3:
            parsed.fields["ingredients"] = {"value": items, "quote": raw[:2000]}
    labels = p.get("labels") or ""
    if labels:
        for field, value in rules_from_text(labels.replace(",", ".\n")).items():
            if field in ("free_from", "claims", "seals"):
                parsed.fields[field] = {"value": value["value"], "quote": f"Open Beauty Facts labels: {labels}"[:2000]}
    return parsed


# --------------------------------------------------------------------------- JSON-LD parser


class JsonLdProduct(Connector):
    name = "jsonld_product"
    label = "Product data on pages (schema.org)"
    description = "Reads schema.org Product data (JSON-LD and microdata) that many retailers embed. Runs on every fetched page."
    source_type = "retailer"
    kind = "parser"


# --------------------------------------------------------------------------- GDELT news


class GdeltNews(Connector):
    name = "gdelt_news"
    label = "News (GDELT)"
    description = "GDELT DOC 2.0: recent news articles mentioning the brand or product."
    source_type = "news"
    kind = "mention"
    interval = 6.0  # GDELT asks for at most one request every 5 seconds
    hosts = ("api.gdeltproject.org",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        query = f'"{brand.name}"' if sku is None else f'"{sku.name.replace(brand.name, "").strip()}" "{brand.name}"'
        res = ctx.http.api(
            "GET",
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": query, "mode": "artlist", "format": "json", "maxrecords": 25, "sort": "datedesc", "timespan": "3months"},
        )
        is_json = "json" in res.headers.get("content-type", "") or res.text.lstrip().startswith("{")
        if res.status_code != 200 or not is_json:
            ctx.note("gdelt_news", query=query, status=res.status_code, error="rate limited or not JSON")
            return []
        try:
            articles = res.json().get("articles", [])
        except ValueError:
            ctx.note("gdelt_news", query=query, error="response was not JSON")
            return []
        out = []
        for a in articles:
            seen = a.get("seendate", "")
            try:
                seen = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").isoformat() + "Z"
            except ValueError:
                pass
            out.append(
                Candidate(
                    url=a.get("url", ""),
                    connector=self.name,
                    source_type="news",
                    kind="mention",
                    title=a.get("title", ""),
                    why=f"news article ({a.get('domain', '')})",
                    data={"seen": seen, "domain": a.get("domain"), "language": a.get("language"), "country": a.get("sourcecountry")},
                )
            )
        return [c for c in out if c.url]


# --------------------------------------------------------------------------- Wikidata

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
FACT_PROPS = {"P127": "owned_by", "P749": "parent_organization", "P571": "founded", "P112": "founded_by", "P17": "country", "P856": "official_website"}


class Wikidata(Connector):
    name = "wikidata"
    label = "Wikidata"
    description = "Brand facts: owner, parent company, founded, founders, country, official website."
    source_type = "entity"
    kind = "entity"
    interval = 1.0
    hosts = ("www.wikidata.org",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        if sku is not None:
            return []  # brand-level facts only
        res = ctx.http.api(
            "GET", WIKIDATA_API, params={"action": "wbsearchentities", "search": brand.name, "language": "en", "type": "item", "limit": 5, "format": "json"}
        )
        hits = res.json().get("search", []) if res.status_code == 200 else []
        hits = [h for h in hits if h.get("label", "").lower() == brand.name.lower()] or hits
        preferred = [h for h in hits if re.search(r"brand|company|cosmetic|skin|care", h.get("description", ""), re.I)]
        if not (preferred or hits):
            return []
        item = (preferred or hits)[0]
        facts = self.facts(ctx, item["id"])
        return [
            Candidate(
                url=f"https://www.wikidata.org/wiki/{item['id']}",
                connector=self.name,
                source_type="entity",
                kind="entity",
                title=item.get("label", brand.name),
                why=item.get("description", "Wikidata item"),
                data={"id": item["id"], "description": item.get("description"), **facts},
            )
        ]

    def facts(self, ctx: Context, qid: str) -> dict[str, Any]:
        res = ctx.http.api("GET", WIKIDATA_API, params={"action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"})
        claims = res.json().get("entities", {}).get(qid, {}).get("claims", {}) if res.status_code == 200 else {}
        raw: dict[str, list[Any]] = {}
        for prop, key in FACT_PROPS.items():
            for c in claims.get(prop, []):
                v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if v is None:
                    continue
                if isinstance(v, dict) and "id" in v:
                    raw.setdefault(key, []).append(v["id"])
                elif isinstance(v, dict) and "time" in v:
                    raw.setdefault(key, []).append(v["time"].lstrip("+")[:4])
                else:
                    raw.setdefault(key, []).append(v)
        ids = sorted({x for vals in raw.values() for x in vals if isinstance(x, str) and re.fullmatch(r"Q\d+", x)})
        labels: dict[str, str] = {}
        if ids:
            res = ctx.http.api(
                "GET", WIKIDATA_API, params={"action": "wbgetentities", "ids": "|".join(ids[:50]), "props": "labels", "languages": "en", "format": "json"}
            )
            for q, ent in (res.json().get("entities", {}) if res.status_code == 200 else {}).items():
                labels[q] = ent.get("labels", {}).get("en", {}).get("value", q)
        return {k: [labels.get(x, x) if isinstance(x, str) else x for x in vals] for k, vals in raw.items()}


# --------------------------------------------------------------------------- keyed search


class BraveSearch(Connector):
    name = "web_search"
    label = "Web search (Brave)"
    description = "Brave Search API: finds retailer pages, reviews and 'best X' articles."
    source_type = "search"
    kind = "finder"
    needs_key = ("BRAVE_API_KEY",)
    interval = 1.1
    hosts = ("api.search.brave.com",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        out = []
        for q in queries:
            res = ctx.http.api(
                "GET",
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": q, "count": 10},
                headers={"X-Subscription-Token": ctx.env["BRAVE_API_KEY"], "Accept": "application/json"},
            )
            if res.status_code != 200:
                ctx.note(self.name, query=q, status=res.status_code)
                continue
            for r in res.json().get("web", {}).get("results", []):
                out.append(_page_candidate(r.get("url", ""), r.get("title", ""), r.get("description", ""), self.name, q, brand))
        return [c for c in out if c.url]


class ExaSearch(Connector):
    name = "exa_search"
    label = "Web search (Exa)"
    description = "Exa search API: finds retailer pages, reviews and articles."
    source_type = "search"
    kind = "finder"
    needs_key = ("EXA_API_KEY",)
    interval = 1.0
    hosts = ("api.exa.ai",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        out = []
        for q in queries:
            res = ctx.http.api(
                "POST",
                "https://api.exa.ai/search",
                json={"query": q, "numResults": 10, "type": "auto"},
                headers={"x-api-key": ctx.env["EXA_API_KEY"]},
            )
            if res.status_code != 200:
                ctx.note(self.name, query=q, status=res.status_code)
                continue
            for r in res.json().get("results", []):
                out.append(_page_candidate(r.get("url", ""), r.get("title") or "", "", self.name, q, brand))
        return [c for c in out if c.url]


def _page_candidate(url: str, title: str, snippet: str, connector: str, query: str, brand: BrandInfo) -> Candidate:
    return Candidate(
        url=url,
        connector=connector,
        source_type=guess_source_type(url, brand),
        kind="page",
        title=title,
        snippet=snippet,
        why=f"search result for “{query}”",
    )


# --------------------------------------------------------------------------- keyed social / video


class Reddit(Connector):
    name = "reddit"
    label = "Reddit"
    description = "Official Reddit API (app-only OAuth): posts mentioning the product."
    source_type = "social"
    kind = "mention"
    needs_key = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
    interval = 1.0
    hosts = ("www.reddit.com", "oauth.reddit.com")

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        tok = ctx.http.api(
            "POST",
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(ctx.env["REDDIT_CLIENT_ID"], ctx.env["REDDIT_CLIENT_SECRET"]),
        )
        if tok.status_code != 200:
            ctx.note(self.name, error=f"token request returned {tok.status_code}")
            return []
        headers = {"Authorization": f"Bearer {tok.json().get('access_token', '')}"}
        out = []
        for q in queries[:2]:
            res = ctx.http.api("GET", "https://oauth.reddit.com/search", params={"q": q, "limit": 25, "sort": "relevance", "type": "link"}, headers=headers)
            if res.status_code != 200:
                ctx.note(self.name, query=q, status=res.status_code)
                continue
            for child in res.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                out.append(
                    Candidate(
                        url=f"https://www.reddit.com{d.get('permalink', '')}",
                        connector=self.name,
                        source_type="social",
                        kind="mention",
                        title=d.get("title", ""),
                        snippet=(d.get("selftext") or "")[:500],
                        why=f"r/{d.get('subreddit', '')} post",
                        data={"subreddit": d.get("subreddit"), "score": d.get("score"), "created_utc": d.get("created_utc")},
                    )
                )
        return out


class YouTube(Connector):
    name = "youtube"
    label = "YouTube"
    description = "YouTube Data API: videos about the product, with descriptions."
    source_type = "video"
    kind = "mention"
    needs_key = ("YOUTUBE_API_KEY",)
    interval = 1.0
    hosts = ("www.googleapis.com",)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        out = []
        for q in queries[:2]:
            res = ctx.http.api(
                "GET",
                "https://www.googleapis.com/youtube/v3/search",
                params={"part": "snippet", "q": q, "type": "video", "maxResults": 10, "key": ctx.env["YOUTUBE_API_KEY"]},
            )
            if res.status_code != 200:
                ctx.note(self.name, query=q, status=res.status_code)
                continue
            for item in res.json().get("items", []):
                vid, sn = item.get("id", {}).get("videoId"), item.get("snippet", {})
                if not vid:
                    continue
                out.append(
                    Candidate(
                        url=f"https://www.youtube.com/watch?v={vid}",
                        connector=self.name,
                        source_type="video",
                        kind="mention",
                        title=sn.get("title", ""),
                        snippet=sn.get("description", "")[:500],
                        why=f"video by {sn.get('channelTitle', '')}",
                        data={"channel": sn.get("channelTitle"), "published": sn.get("publishedAt")},
                    )
                )
        return out


# --------------------------------------------------------------------------- marketplaces, readers


class Amazon(Connector):
    name = "amazon"
    label = "Amazon (licensed data)"
    description = "Amazon listings through a licensed provider (Keepa or Rainforest). amazon.com is never scraped."
    source_type = "retailer"
    kind = "page"

    def key_present(self, env: dict[str, str] | None = None) -> bool:
        import os

        env = os.environ if env is None else env
        return bool(env.get("KEEPA_API_KEY") or env.get("RAINFOREST_API_KEY"))

    def availability(self, env: dict[str, str]) -> str | None:
        if not self.key_present(env):
            return "missing KEEPA_API_KEY or RAINFOREST_API_KEY"
        return "licensed provider integration not built yet (stub)"


class JinaReader(Connector):
    name = "jina_reader"
    label = "Jina Reader"
    description = "Turns JavaScript-heavy pages into clean text when a direct fetch gets too little. Last step of the fetch chain; robots.txt is still checked first."
    source_type = "reader"
    kind = "reader"
    needs_key = ("JINA_API_KEY",)
    key_optional = True
    hosts = ("r.jina.ai",)

    def prepare(self, ctx: Context) -> None:
        # Keyless use is heavily rate-limited by Jina; stay well under it.
        ctx.http.set_interval("r.jina.ai", 1.0 if ctx.env.get("JINA_API_KEY") else 10.0)


class RenderedFetch(Connector):
    name = "rendered"
    label = "Headless browser fetch"
    description = "Renders a page in headless Chromium (Playwright) when a direct fetch returns too little. Needs the Playwright package and browser installed."
    source_type = "reader"
    kind = "reader"

    def availability(self, env: dict[str, str]) -> str | None:
        from app.collector.fetchers import render_available

        return None if render_available() else "Playwright is not installed (optional)"


ALL: list[Connector] = [
    BrandSite(),
    OpenBeautyFacts(),
    JsonLdProduct(),
    GdeltNews(),
    Wikidata(),
    BraveSearch(),
    ExaSearch(),
    Reddit(),
    YouTube(),
    Amazon(),
    RenderedFetch(),
    JinaReader(),
]
BY_NAME = {c.name: c for c in ALL}
