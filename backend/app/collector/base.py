"""Connector interface and the small data types passed between collector steps."""

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.collector.http import Fetched, PoliteClient

if TYPE_CHECKING:
    from app.collector.llm import Claude


@dataclass
class BrandInfo:
    id: int
    name: str
    site_url: str | None  # brand domain, from the truth sheet's evidence URL


@dataclass
class SkuInfo:
    id: int
    name: str
    gtin: str | None
    line: str | None


@dataclass
class Parsed:
    """Claim fields read from one source: {field: {"value": ..., "quote": "..."}}."""

    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    name: str | None = None
    gtin: str | None = None
    method: str = ""  # jsonld | open_beauty_facts | text_rules | llm (joined with +)


@dataclass
class Candidate:
    url: str
    connector: str
    source_type: str  # brand | database | retailer | review | article | news | entity | social | video
    kind: str  # page (compared to the truth) | mention | entity
    title: str = ""
    why: str = ""
    snippet: str = ""
    gtin: str | None = None
    data: dict[str, Any] | None = None
    parsed: Parsed | None = None  # filled directly by API connectors (e.g. Open Beauty Facts)


@dataclass
class Context:
    http: PoliteClient
    env: dict[str, str]
    claude: "Claude | None" = None
    enabled: set[str] = field(default_factory=set)  # connector names that may run
    log: list[dict[str, Any]] = field(default_factory=list)
    cache: dict[str, Any] = field(default_factory=dict)  # per-run, e.g. sitemap URLs per brand site

    def note(self, step: str, **detail: Any) -> None:
        self.log.append({"step": step, **detail})


class Connector:
    name = ""
    label = ""
    description = ""
    source_type = ""
    kind = "page"  # page | mention | entity | finder (finds pages) | reader (fetch fallback) | parser
    needs_key: tuple[str, ...] = ()  # env vars, all required
    key_optional = False  # works without the key at a stricter rate
    interval = 2.0  # seconds between requests to this connector's host(s)
    weight = 1.0  # importance of pages from this source in the score
    hosts: tuple[str, ...] = ()

    def key_present(self, env: dict[str, str] | None = None) -> bool:
        env = os.environ if env is None else env
        return all(env.get(k) for k in self.needs_key)

    def availability(self, env: dict[str, str]) -> str | None:
        """None if the connector can run, else the reason it is skipped."""
        if self.needs_key and not self.key_present(env) and not self.key_optional:
            return f"missing {' and '.join(self.needs_key)}"
        return None

    def prepare(self, ctx: Context) -> None:
        for host in self.hosts:
            ctx.http.set_interval(host, self.interval)

    def discover(self, ctx: Context, brand: BrandInfo, sku: SkuInfo | None, queries: list[str]) -> list[Candidate]:
        return []

    def fetch(self, ctx: Context, candidate: Candidate) -> Fetched | None:
        """Default: the shared fetch chain (direct -> rendered -> Jina Reader)."""
        from app.collector.fetchers import fetch_page

        return fetch_page(ctx, candidate.url)

    def parse(self, fetched: Fetched, candidate: Candidate) -> Parsed | None:
        from app.collector.extract import extract_page

        return extract_page(fetched)
