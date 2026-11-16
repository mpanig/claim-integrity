"""Polite HTTP: robots.txt, per-domain rate limits, retries with backoff, a request budget.

Every request the collector makes goes through PoliteClient.
"""

import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

USER_AGENT = "claim-integrity-collector/0.1 (product claim consistency checks; respects robots.txt)"
DEFAULT_INTERVAL = 2.0  # seconds between requests to the same host
RETRY_STATUSES = {429, 500, 502, 503, 504}

# Never fetched directly, whatever the connector (terms forbid scraping; use licensed data).
BLOCKED_HOSTS = ("amazon.", "walmart.com")

TRACKING_PARAMS = {"gclid", "fbclid", "msclkid", "ref", "ref_"}


class BudgetExceeded(Exception):
    pass


class Blocked(Exception):
    """robots.txt or our own policy forbids this URL."""


@dataclass
class Fetched:
    url: str
    final_url: str
    status: int
    text: str
    content_type: str
    via: str = "direct"  # direct | rendered | jina_reader


def canonical_url(url: str) -> str:
    """Lowercase scheme/host, drop fragments, tracking params and trailing slashes, for dedupe."""
    parts = urlsplit(url.strip())
    query = "&".join(
        q for q in parts.query.split("&") if q and not (q.split("=")[0].lower().startswith("utm_") or q.split("=")[0].lower() in TRACKING_PARAMS)
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_blocked_host(url: str) -> bool:
    host = host_of(url)
    return any(b in host for b in BLOCKED_HOSTS)


@dataclass
class PoliteClient:
    """httpx wrapper. `transport`, `sleep` and `clock` are injectable for tests."""

    budget: int = 50
    user_agent: str = USER_AGENT
    timeout: float = 20.0
    retries: int = 2
    transport: httpx.BaseTransport | None = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    intervals: dict[str, float] = field(default_factory=dict)  # host -> min seconds between requests
    used: int = 0
    log: list[dict[str, Any]] = field(default_factory=list)
    _last: dict[str, float] = field(default_factory=dict)
    _robots: dict[str, urllib.robotparser.RobotFileParser | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.user_agent},
            transport=self.transport,
        )

    def close(self) -> None:
        self.client.close()

    # --- politeness -------------------------------------------------------

    def set_interval(self, host: str, seconds: float) -> None:
        self.intervals[host] = max(self.intervals.get(host, 0.0), seconds)

    def _wait_turn(self, host: str) -> None:
        interval = self.intervals.get(host, DEFAULT_INTERVAL)
        last = self._last.get(host)
        if last is not None:
            wait = interval - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self._last[host] = self.clock()

    def spend(self) -> None:
        """Count one request against the run budget (raises BudgetExceeded when used up)."""
        if self.used >= self.budget:
            raise BudgetExceeded(f"request budget of {self.budget} used up")
        self.used += 1

    def robots_allows(self, url: str) -> bool:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                res = self._request("GET", f"{root}/robots.txt", check_robots=False)
                if res.status_code >= 400:
                    parser = None  # no robots.txt: everything allowed
                else:
                    parser.parse(res.text.splitlines())
            except (httpx.HTTPError, BudgetExceeded):
                parser = None
            self._robots[root] = parser
        parser = self._robots[root]
        return True if parser is None else parser.can_fetch(self.user_agent, url)

    def sitemaps_for(self, url: str) -> list[str]:
        """Sitemap URLs declared in robots.txt (fetches robots.txt if needed)."""
        self.robots_allows(url)
        parts = urlsplit(url)
        parser = self._robots.get(f"{parts.scheme}://{parts.netloc}")
        return list(parser.site_maps() or []) if parser else []

    # --- requests ---------------------------------------------------------

    def _request(self, method: str, url: str, *, check_robots: bool = True, **kwargs: Any) -> httpx.Response:
        if is_blocked_host(url):
            raise Blocked(f"{host_of(url)} is never fetched directly; use a licensed data provider")
        if check_robots and not self.robots_allows(url):
            raise Blocked(f"robots.txt disallows {url}")
        host = host_of(url)
        attempt = 0
        while True:
            self.spend()
            self._wait_turn(host)
            try:
                res = self.client.request(method, url, **kwargs)
            except httpx.TransportError as e:
                self.log.append({"url": url, "error": type(e).__name__})
                if attempt >= self.retries:
                    raise
            else:
                self.log.append({"url": url, "status": res.status_code})
                if res.status_code not in RETRY_STATUSES or attempt >= self.retries:
                    return res
                retry_after = res.headers.get("retry-after", "")
                if retry_after.isdigit():
                    self.sleep(min(int(retry_after), 60))
            attempt += 1
            # Exponential backoff, never shorter than the host's own interval.
            self.sleep(min(max(2**attempt, 2 * self.intervals.get(host, DEFAULT_INTERVAL)), 30))

    def get_html(self, url: str) -> Fetched:
        """GET a web page, obeying robots.txt."""
        res = self._request("GET", url)
        return Fetched(
            url=url,
            final_url=str(res.url),
            status=res.status_code,
            text=res.text,
            content_type=res.headers.get("content-type", ""),
        )

    def api(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Call a documented public API. robots.txt is for crawlers of web pages, so APIs skip it."""
        return self._request(method, url, check_robots=False, **kwargs)
