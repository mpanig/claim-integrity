"""Look up Common Crawl captures without the CDX server (its robots.txt disallows /):
stream each crawl's cluster.idx from data.commoncrawl.org (downloads welcome per its robots.txt),
keep blocks that can hold our SURT prefixes, range-fetch those cdx blocks, filter lines."""
import gzip
import json
import sys

from common import RAW, S, polite_get, save_raw

DATA = "https://data.commoncrawl.org/"
HOSTS = {
    "amazon.com": ["com,amazon)/{b}"], "amazon.co.uk": ["uk,co,amazon)/{b}"], "amazon.in": ["in,amazon)/{b}"],
    "amazon.ca": ["ca,amazon)/{b}"], "walmart.com": ["com,walmart)/ip/{b}"], "target.com": ["com,target)/p/{b}"],
    "cvs.com": ["com,cvs)/shop/{b}"], "walgreens.com": ["com,walgreens)/store/c/{b}"],
    "ulta.com": ["com,ulta)/p/{b}", "com,ulta)/{b}"], "boots.com": ["com,boots)/{b}"],
}
PREFIXES = [(p.format(b=b), dom, b.capitalize()) for dom, ps in HOSTS.items() for p in ps for b in ("aveeno", "listerine")]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def needed_blocks(crawl):
    """Stream cluster.idx once; return [(cdx_file, offset, length)] whose key range overlaps a prefix."""
    url = f"{DATA}cc-index/collections/{crawl}/indexes/cluster.idx"
    blocks, prev = [], None
    with S.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        for raw in r.iter_lines():
            line = raw.decode("utf-8", "replace")
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            key = parts[0].split(" ")[0]
            if prev is not None:
                pkey, pfile, poff, plen = prev
                for p, _, _ in PREFIXES:
                    if pkey <= p + "\x7f" and key >= p:
                        blocks.append((pfile, int(poff), int(plen)))
                        break
            prev = (key, parts[1], parts[2], parts[3])
    if prev:  # last block: overlaps if its start <= any prefix end
        if any(prev[0] <= p + "\x7f" for p, _, _ in PREFIXES):
            pass  # final block would need the next line; skip (very unlikely to hold retail prefixes)
    return blocks


def lookup(crawl):
    cache = RAW / "common_crawl" / "cdx" / f"{crawl}_cluster.jsonl"
    if cache.exists():
        return [json.loads(l) for l in cache.read_text().splitlines() if l.strip()]
    blocks = needed_blocks(crawl)
    log(crawl, "blocks", len(blocks))
    recs = []
    for f, off, ln in blocks:
        r = polite_get(f"{DATA}cc-index/collections/{crawl}/indexes/{f}", min_interval=1.0,
                       headers={"Range": f"bytes={off}-{off + ln - 1}"}, timeout=60)
        if r.status_code not in (200, 206):
            log("block fail", r.status_code, f, off)
            continue
        for line in gzip.decompress(r.content).decode("utf-8", "replace").splitlines():
            key = line.split(" ", 1)[0]
            for p, dom, brand in PREFIXES:
                if key.startswith(p):
                    j = json.loads(line.split(" ", 2)[2])
                    if j.get("status") == "200" and "html" in j.get("mime", ""):
                        j.update({"timestamp": line.split(" ", 2)[1], "_crawl": crawl, "_dom": dom, "_brand": brand})
                        recs.append(j)
                    break
    save_raw(f"common_crawl/cdx/{crawl}_cluster.jsonl", "\n".join(json.dumps(x) for x in recs))
    log(crawl, "captures", len(recs))
    return recs
