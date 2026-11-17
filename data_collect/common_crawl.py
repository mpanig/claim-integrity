"""Common Crawl: CDX prefix queries for retailer product slugs, then WARC byte-range fetches."""
import gzip
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from warcio.archiveiterator import ArchiveIterator

from common import RAW, allowed, extract_page, polite_get, save_raw, slug

N_CRAWLS = 12
MAX_WARC = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
# SURT canonicalisation lowercases URLs, so one lowercase prefix per pattern is enough.
PATTERNS = {
    "amazon.com": ["www.amazon.com/{b}"], "amazon.co.uk": ["www.amazon.co.uk/{b}"],
    "amazon.in": ["www.amazon.in/{b}"], "amazon.ca": ["www.amazon.ca/{b}"],
    "walmart.com": ["www.walmart.com/ip/{b}"], "target.com": ["www.target.com/p/{b}"],
    "cvs.com": ["www.cvs.com/shop/{b}"], "walgreens.com": ["www.walgreens.com/store/c/{b}"],
    "ulta.com": ["www.ulta.com/p/{b}", "www.ulta.com/{b}"], "boots.com": ["www.boots.com/{b}"],
}
LOCALE = {"amazon.co.uk": "en-GB", "amazon.in": "en-IN", "amazon.ca": "en-CA", "boots.com": "en-GB"}
BLOCK_RE = re.compile(r"robot check|captcha|access denied|page not found|sorry|are you a human|blocked", re.I)
CDX_DIR = RAW / "common_crawl" / "cdx"
WARC_DIR = RAW / "common_crawl" / "html"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def cdx_query(api, pat):
    rel = f"{api.rsplit('/', 1)[-1]}_{slug(pat)}.jsonl"
    cache = CDX_DIR / rel
    if cache.exists():
        return [json.loads(l) for l in cache.read_text().splitlines() if l.strip()]
    base = f"{api}?url={quote(pat)}*&output=json&filter=status:200&filter=mime:text/html"
    recs, page, pages = [], 0, 1
    while page < pages:
        r = None
        for attempt in range(3):
            try:
                r = polite_get(base + f"&page={page}", min_interval=2.0, timeout=120)
            except Exception as e:
                log("CDX ERR", pat, str(e)[:80])
                time.sleep(15)
                continue
            if r.status_code in (502, 504):
                time.sleep(10)
                continue
            break
        if r is None:
            return None
        if r.status_code == 404:  # "No Captures found"
            break
        if not r.ok:
            log("CDX FAIL", r.status_code, pat, api)
            return None
        recs += [json.loads(l) for l in r.text.splitlines() if l.strip()]
        if page == 0 and len(recs) >= 14000:  # possible more pages
            n = polite_get(base + "&showNumPages=true", min_interval=2.0, timeout=120)
            try:
                pages = int(n.json().get("pages", 1))
            except Exception:
                pages = 1
        page += 1
    save_raw(f"common_crawl/cdx/{rel}", "\n".join(json.dumps(x) for x in recs))
    return recs


def fetch_warc(rec):
    off, ln = int(rec["offset"]), int(rec["length"])
    url = "https://data.commoncrawl.org/" + rec["filename"]
    r = polite_get(url, min_interval=1.0, headers={"Range": f"bytes={off}-{off + ln - 1}"}, timeout=60)
    if r.status_code not in (200, 206):
        return None, f"http {r.status_code}"
    for record in ArchiveIterator(io.BytesIO(r.content)):
        if record.rec_type == "response":
            body = record.content_stream().read()
            ct = record.http_headers.get_header("Content-Type") or ""
            m = re.search(r"charset=([\w-]+)", ct)
            enc = m.group(1) if m else "utf-8"
            try:
                return body.decode(enc, errors="replace"), None
            except LookupError:
                return body.decode("utf-8", errors="replace"), None
    return None, "no response record"


def main(out_path):
    import cc_index
    # collinfo.json is explicitly allowed by index.commoncrawl.org/robots.txt; the CDX API is not,
    # so lookups go through cc_index (index shards on data.commoncrawl.org).
    coll = json.loads((RAW / "common_crawl" / "collinfo.json").read_text())
    crawls = [c["id"] for c in coll[:24]]  # ~2 years of monthly-ish crawls
    log("crawls:", crawls)
    caps = {}
    stats = {"index_fail": 0, "crawls": crawls}
    for cid in crawls:
        try:
            recs = cc_index.lookup(cid)
        except Exception as e:
            log("index fail", cid, str(e)[:120])
            stats["index_fail"] += 1
            continue
        for rec in recs:
            caps[(rec["url"], rec["timestamp"])] = rec
    log("total captures", len(caps), "unique urls", len({k[0] for k in caps}))
    by_dom = {}
    for rec in caps.values():
        by_dom.setdefault(rec["_dom"], []).append(rec)
    for v in by_dom.values():
        v.sort(key=lambda r: (r["url"], r["timestamp"]))
    queue = []  # round-robin across retailers so a cap doesn't starve any of them
    while any(by_dom.values()):
        for d in list(by_dom):
            if by_dom[d]:
                queue.append(by_dom[d].pop(0))
    log("queue", len(queue), "cap", MAX_WARC)
    stats.update({"captures": len(caps), "fetched": 0, "fetch_fail": 0, "blocked_or_empty": 0, "rows": 0})
    with open(out_path, "w", encoding="utf-8") as out:
        for i, rec in enumerate(queue[:MAX_WARC]):
            cached = WARC_DIR / rec["_dom"] / f"{slug(rec['url'])}_{rec['timestamp']}.html.gz"
            if cached.exists():
                html, err = gzip.decompress(cached.read_bytes()).decode("utf-8"), None
            else:
                try:
                    html, err = fetch_warc(rec)
                except Exception as e:
                    html, err = None, str(e)[:100]
            if html is None:
                stats["fetch_fail"] += 1
                continue
            stats["fetched"] += 1
            ex = extract_page(html)
            if BLOCK_RE.search(ex["title"][:80]) and not ex["description"] and not ex["claims"]:
                stats["blocked_or_empty"] += 1
                continue
            if not (ex["description"] or ex["claims"] or ex["title"]):
                stats["blocked_or_empty"] += 1
                continue
            raw = WARC_DIR / rec["_dom"] / f"{slug(rec['url'])}_{rec['timestamp']}.html.gz"
            raw.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(gzip.compress(html.encode("utf-8")))
            ts = datetime.strptime(rec["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            row = {
                "brand": rec["_brand"], "product_name": ex["name"], "gtin": ex["gtin"],
                "source_type": "common_crawl_retailer", "source_domain": rec["_dom"], "url": rec["url"],
                "captured_at": ts.isoformat(), "locale": LOCALE.get(rec["_dom"], "en-US"),
                "title": ex["title"], "description": ex["description"], "claims": ex["claims"],
                "ingredients": ex["ingredients"], "raw_path": str(raw),
                "extra": {"crawl": rec["_crawl"], "warc": rec["filename"], "offset": rec["offset"],
                          "length": rec["length"], "meta_description": ex["meta_description"]},
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            stats["rows"] += 1
            if i % 100 == 0:
                log("progress", i, stats)
    json.dump(stats, open("out/common_crawl_stats.json", "w"), indent=1)
    log("DONE", stats)


if __name__ == "__main__":
    main(sys.argv[1])
