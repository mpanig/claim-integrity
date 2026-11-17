"""Check the per-table CSVs against the schema: column order, NOT NULL, varchar lengths, JSON, ISO timestamps,
FK ids present, unique page.url, ids unique. usage: validate.py DIR"""
import csv
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(10**9)
D = Path(sys.argv[1])
SCHEMA = {  # col: (not_null, maxlen|None, kind)
    "organisation": {"id": (1, None, "int"), "name": (1, 200, "s"), "created_at": (1, None, "ts")},
    "brand": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "name": (1, 200, "s"),
              "aliases": (1, None, "json"), "positioning": (1, None, "json")},
    "sku": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "brand_id": (1, None, "int"),
            "gtin": (0, 14, "s"), "name": (1, 300, "s"), "line": (0, 200, "s"), "last_checked_at": (0, None, "ts"),
            "aliases": (1, None, "json")},
    "variant": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "sku_id": (1, None, "int"),
                "market": (1, 8, "s"), "size": (0, 50, "s"), "formula_version": (0, 50, "s"),
                "valid_from": (0, None, "date"), "valid_to": (0, None, "date")},
    "page": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "url": (1, None, "s"),
             "source_type": (1, 30, "s"), "retailer": (0, 100, "s"), "country": (0, 2, "s"), "weight": (1, None, "float")},
    "snapshot": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "page_id": (1, None, "int"),
                 "fetched_at": (1, None, "ts"), "content_hash": (1, 64, "s"), "html": (1, None, "s")},
    "extraction": {"id": (1, None, "int"), "organisation_id": (1, None, "int"), "snapshot_id": (1, None, "int"),
                   "sku_id": (1, None, "int"), "fields": (1, None, "json"), "created_at": (1, None, "ts")},
    "inferred_truth": {"id": (1, None, "int"), "sku_id": (1, None, "int"), "fields": (1, None, "json"),
                       "agreement": (1, None, "json"), "method": (1, 20, "s"), "sources": (1, None, "int"),
                       "source_hash": (0, 64, "s"), "updated_at": (1, None, "ts")},
}
FK = {"brand": {"organisation_id": "organisation"},
      "sku": {"organisation_id": "organisation", "brand_id": "brand"},
      "variant": {"organisation_id": "organisation", "sku_id": "sku"},
      "page": {"organisation_id": "organisation"},
      "snapshot": {"organisation_id": "organisation", "page_id": "page"},
      "extraction": {"organisation_id": "organisation", "snapshot_id": "snapshot", "sku_id": "sku"},
      "inferred_truth": {"sku_id": "sku"}}


def files(t):
    if t == "snapshot":
        return sorted(D.glob("snapshot_part*.csv.gz"))
    return [D / f"{t}.csv"]


ids, errors, counts = {}, [], {}
for t, cols in SCHEMA.items():
    ids[t] = set()
    n = 0
    for f in files(t):
        op = gzip.open if f.suffix == ".gz" else open
        with op(f, "rt", encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd)
            if header != list(cols):
                errors.append(f"{f.name}: header {header} != {list(cols)}")
            for row in rd:
                n += 1
                rec = dict(zip(header, row))
                for c, (nn, ml, kind) in cols.items():
                    v = rec.get(c, "")
                    if v == "":
                        if nn:
                            errors.append(f"{t} id={rec.get('id')}: {c} NULL")
                        continue
                    if ml and len(v) > ml:
                        errors.append(f"{t} id={rec.get('id')}: {c} len {len(v)} > {ml}")
                    try:
                        if kind == "int":
                            int(v)
                        elif kind == "float":
                            float(v)
                        elif kind == "json":
                            json.loads(v)
                        elif kind == "ts":
                            datetime.fromisoformat(v)
                        elif kind == "date":
                            datetime.strptime(v, "%Y-%m-%d")
                    except Exception as e:
                        errors.append(f"{t} id={rec.get('id')}: {c} bad {kind}: {v[:40]}")
                if rec["id"] in ids[t]:
                    errors.append(f"{t}: duplicate id {rec['id']}")
                ids[t].add(rec["id"])
                for c, ref in FK.get(t, {}).items():
                    if rec[c] not in ids[ref]:
                        errors.append(f"{t} id={rec['id']}: {c}={rec[c]} missing in {ref}")
                if "\x00" in "".join(row):
                    errors.append(f"{t} id={rec['id']}: NUL byte")
    counts[t] = n
its = [r["sku_id"] for r in csv.DictReader(open(D / "inferred_truth.csv", encoding="utf-8"))]
if len(its) != len(set(its)):
    errors.append("inferred_truth.sku_id not unique")
urls = [r["url"] for r in csv.DictReader(open(D / "page.csv", encoding="utf-8"))]
if len(urls) != len(set(urls)):
    errors.append("page.url not unique")
print(json.dumps(counts))
print(f"{len(errors)} errors")
print("\n".join(errors[:40]))
sys.exit(1 if errors else 0)
