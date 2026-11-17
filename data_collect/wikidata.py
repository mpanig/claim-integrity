"""Wikidata (optional, small): brand/product items whose label names the brand, all-language labels+descriptions.
SPARQL endpoint returned 504s, so this uses the plain wbsearchentities + wbgetentities API."""
import json
import sys
from datetime import datetime, timezone

from common import clean, polite_get, save_raw

BRANDS = ["Aveeno", "Listerine"]
API = "https://www.wikidata.org/w/api.php"


def main(out_path):
    rows = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for brand in BRANDS:
        r = polite_get(f"{API}?action=wbsearchentities&search={brand}&language=en&format=json&limit=20")
        save_raw(f"wikidata/search_{brand}.json", r.text)
        hits = [h for h in r.json().get("search", []) if brand.lower() in h.get("label", "").lower()]
        qids = [h["id"] for h in hits]
        print(brand, qids, file=sys.stderr)
        if not qids:
            continue
        r = polite_get(f"{API}?action=wbgetentities&ids={'|'.join(qids)}&props=labels|descriptions|claims&format=json")
        save_raw(f"wikidata/entities_{brand}.json", r.text)
        for qid, ent in r.json().get("entities", {}).items():
            gtins = [c["mainsnak"].get("datavalue", {}).get("value", "") for c in ent.get("claims", {}).get("P3962", [])]
            descs = ent.get("descriptions", {})
            for lang, lab in ent.get("labels", {}).items():
                rows.append({
                    "brand": brand, "product_name": clean(lab["value"]), "gtin": gtins[0] if gtins else "",
                    "source_type": "wikidata", "source_domain": "wikidata.org",
                    "url": f"https://www.wikidata.org/wiki/{qid}", "captured_at": now, "locale": lang,
                    "title": clean(lab["value"]), "description": clean(descs.get(lang, {}).get("value", "")),
                    "claims": [], "ingredients": "", "extra": {"qid": qid},
                })
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("wikidata rows", len(rows), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
