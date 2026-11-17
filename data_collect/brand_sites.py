"""Brand sites: robots.txt -> sitemaps -> allowed product pages -> extracted fields."""
import gzip
import json
import re
import sys
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from common import RAW, UA, allowed, extract_page, fix_mojibake, polite_get, robots_for, save_raw, slug

DOMAINS = {
    "Aveeno": ["aveeno.com", "aveeno.ca", "aveeno.co.uk", "aveeno.com.au", "aveeno.in", "aveeno.de",
               "aveeno.fr", "aveeno.es", "aveeno.it", "aveeno.co.za", "aveeno.co.nz", "aveeno.com.br"],
    "Listerine": ["listerine.com", "listerine.ca", "listerine.co.uk", "listerine.com.au", "listerine.in",
                  "listerine.de", "listerine.fr", "listerine.es", "listerine.it", "listerine.co.nz",
                  "listerine.com.br", "listerine.co.za"],
}
PRODUCT_RE = re.compile(r"/(products?|produkte?|produits?|productos?|prodotti|produtos)/[^?#]+", re.I)
SKIP_RE = re.compile(r"\.(jpg|png|pdf|webp)$|/(category|categories|collections?|tags?)/", re.I)
AU_RE = re.compile(r"^/[a-z-]+-care/(?!collections/)[a-z0-9-]+/[a-z0-9-]+/?$", re.I)  # aveeno.com.au style
CAP = 500
log_lock = threading.Lock()
report = {}


def log(*a):
    with log_lock:
        print(*a, file=sys.stderr, flush=True)


def resolve_base(domain):
    for cand in (f"https://www.{domain}", f"https://{domain}"):
        try:
            r = polite_get(cand + "/", allow_redirects=True)
        except Exception:
            continue
        if r.status_code < 500:
            p = urlparse(r.url)
            return f"{p.scheme}://{p.netloc}", r.status_code
    return None, None


def sitemap_urls(base, rp_text):
    maps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rp_text or "") or [base + "/sitemap.xml"]
    seen, locs, todo = set(), [], list(maps)
    while todo and len(seen) < 60:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            r = polite_get(sm)
        except Exception:
            continue
        if not r.ok:
            continue
        body = r.content
        if sm.endswith(".gz"):
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        save_raw(f"brand_sites/sitemaps/{urlparse(sm).netloc}_{slug(sm)}.xml", body)
        soup = BeautifulSoup(body, "xml")
        if soup.find("sitemapindex"):
            todo += [l.get_text(strip=True) for l in soup.select("sitemap > loc")]
        else:
            for u in soup.find_all("url"):
                loc = u.find("loc")
                lm = u.find("lastmod")
                if loc:
                    locs.append((loc.get_text(strip=True), lm.get_text(strip=True) if lm else ""))
    return locs


def do_domain(brand, domain, out):
    base, status = resolve_base(domain)
    if not base:
        report[domain] = "unreachable"
        log(domain, "unreachable")
        return
    host = urlparse(base).netloc
    rp = robots_for(base)
    if rp is None:
        report[domain] = f"robots.txt unavailable ({base}); skipped"
        log(domain, "robots unavailable, skipped")
        return
    try:
        rp_text = (RAW / "robots" / f"{host}.txt").read_text(encoding="utf-8")
    except OSError:
        rp_text = ""
    locs = sitemap_urls(base, rp_text)
    cands = [(u, lm) for u, lm in locs if (PRODUCT_RE.search(urlparse(u).path) or AU_RE.search(urlparse(u).path))
             and not SKIP_RE.search(u) and domain in urlparse(u).netloc]
    cands = list(dict.fromkeys(cands))
    ok_cands = [(u, lm) for u, lm in cands if allowed(u)]
    log(f"{domain} base={base} sitemap_urls={len(locs)} product_cands={len(cands)} allowed={len(ok_cands)}")
    n_ok = n_fail = 0
    for u, lm in ok_cands[:CAP]:
        cached = RAW / "brand_sites" / "pages" / host / f"{slug(u)}.html"
        if cached.exists():  # fetched in the first pass; repair its Latin-1 mis-decoding
            text = fix_mojibake(cached.read_text(encoding="utf-8"))
            cached.write_text(text, encoding="utf-8")
            final_url = u
            captured = datetime.fromtimestamp(cached.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
        else:
            try:
                r = polite_get(u)
            except Exception:
                n_fail += 1
                continue
            if not r.ok or "html" not in r.headers.get("content-type", ""):
                n_fail += 1
                continue
            text, final_url = r.text, r.url
            cached = save_raw(f"brand_sites/pages/{host}/{slug(u)}.html", text)
            captured = datetime.now(timezone.utc).isoformat(timespec="seconds")
        raw = cached
        ex = extract_page(text)
        html_lang = re.search(r"<html[^>]*\blang=[\"']?([\w-]+)", text[:5000], re.I)
        row = {
            "brand": brand, "product_name": ex["name"], "gtin": ex["gtin"], "source_type": "brand_site",
            "source_domain": host, "url": final_url,
            "captured_at": captured,
            "locale": html_lang.group(1) if html_lang else "", "title": ex["title"],
            "description": ex["description"], "claims": ex["claims"], "ingredients": ex["ingredients"],
            "raw_path": str(raw), "extra": {"sitemap_lastmod": lm, "meta_description": ex["meta_description"],
                                            "og_description": ex["og_description"]},
        }
        with log_lock:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
        n_ok += 1
    report[domain] = f"base={base} sitemap={len(locs)} cands={len(cands)} allowed={len(ok_cands)} fetched={n_ok} failed={n_fail}"
    log(domain, "done", n_ok, n_fail)


def main(out_path):
    with open(out_path, "w", encoding="utf-8") as out:
        threads = [threading.Thread(target=do_domain, args=(b, d, out)) for b, ds in DOMAINS.items() for d in ds]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    json.dump(report, open("out/brand_sites_report.json", "w"), indent=1)
    log(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
