"""Cut the next self-contained chunk from a full build.

Each chunk holds ~SIZE not-yet-pushed snapshots (each snapshot/extraction belongs to exactly one chunk) plus every
parent row they need (organisation, brand, sku, variant, page) and the inferred_truth of their products, with the
same stable ids in every chunk (id registry). load_order.sql loads each table through a staging table with
ON CONFLICT DO NOTHING (inferred_truth: DO UPDATE when newer), so chunks load alone, in any order, and twice.

usage: chunk.py FULL_DIR REGISTRY CHUNK_ROOT SIZE
"""
import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

csv.field_size_limit(10**9)
FULL, REG_P, ROOT, SIZE = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
REG = json.loads(REG_P.read_text(encoding="utf-8"))
st = REG.setdefault("_chunks", {"n": 0, "snapshots": {}, "unmatched": {}})

COLS = {
    "organisation": ["id", "name", "created_at"],
    "brand": ["id", "organisation_id", "name", "aliases", "positioning"],
    "sku": ["id", "organisation_id", "brand_id", "gtin", "name", "line", "last_checked_at", "aliases"],
    "variant": ["id", "organisation_id", "sku_id", "market", "size", "formula_version", "valid_from", "valid_to"],
    "page": ["id", "organisation_id", "url", "source_type", "retailer", "country", "weight"],
    "snapshot": ["id", "organisation_id", "page_id", "fetched_at", "content_hash", "html"],
    "extraction": ["id", "organisation_id", "snapshot_id", "sku_id", "fields", "created_at"],
    "inferred_truth": ["id", "sku_id", "fields", "agreement", "method", "sources", "source_hash", "updated_at"],
}


def read(name):
    with open(FULL / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header])


ext = read("extraction.csv")
pushed = st["snapshots"]
todo = sorted((int(e["snapshot_id"]) for e in ext if e["snapshot_id"] not in pushed))
if not todo:
    sys.exit("nothing new to chunk")
take = todo if len(todo) - SIZE < SIZE * 0.25 else todo[:SIZE]
S = {str(i) for i in take}
no = st["n"] + 1
OUT = ROOT / f"chunk_{no:03d}"
OUT.mkdir(parents=True, exist_ok=False)

ext_c = [e for e in ext if e["snapshot_id"] in S]
skus = {e["sku_id"] for e in ext_c}
sidx = {r["snapshot_id"]: r for r in read("snapshot_index.csv")}
pages = {sidx[s]["page_id"] for s in S}
sku_rows = [r for r in read("sku.csv") if r["id"] in skus]
brands = {r["brand_id"] for r in sku_rows}
tables = {
    "organisation": read("organisation.csv"),
    "brand": [r for r in read("brand.csv") if r["id"] in brands],
    "sku": sku_rows,
    "variant": [r for r in read("variant.csv") if r["sku_id"] in skus],
    "page": [r for r in read("page.csv") if r["id"] in pages],
    "extraction": ext_c,
    "inferred_truth": [r for r in read("inferred_truth.csv") if r["sku_id"] in skus],
}
for t, rows in tables.items():
    write(OUT / f"{t}.csv", COLS[t], rows)

# snapshot html: stream the full parts, keep this chunk's rows, split into <45 MB gz parts
parts, out_f, out_w, n_bytes = [], None, None, 0
for p in sorted(FULL.glob("snapshot_part*.csv.gz")):
    with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["id"] not in S:
                continue
            if out_f is None or n_bytes > 180 * 1024 * 1024:
                if out_f:
                    out_f.close()
                parts.append(f"snapshot_part{len(parts) + 1:02d}.csv.gz")
                out_f = gzip.open(OUT / parts[-1], "wt", encoding="utf-8", newline="")
                out_w = csv.writer(out_f)
                out_w.writerow(COLS["snapshot"])
                n_bytes = 0
            out_w.writerow([r[h] for h in COLS["snapshot"]])
            n_bytes += len(r["html"])
out_f.close()

# flat rows: this chunk's loadable rows + unmatched rows not shipped before; plus the match audit
rpm = [r for r in read("row_product_match.csv") if r["snapshot_id"] in S]
keys = {r["row_key"] for r in rpm}
um_all = read("unmatched_rows.csv")
um_new = [r for r in um_all if r["row_key"] not in st["unmatched"]]
with open(FULL / "aveeno_listerine_descriptions.csv", encoding="utf-8", newline="") as f:
    rd = csv.DictReader(f)
    flat_hdr = rd.fieldnames
    flat = [r for r in rd if r["row_key"] in keys or (not r["sku_id"] and r["row_key"] not in st["unmatched"])]
write(OUT / "aveeno_listerine_descriptions.csv", flat_hdr, flat)
write(OUT / "unmatched_rows.csv", list(um_all[0].keys()) if um_all else flat_hdr, um_new)
write(OUT / "row_product_match.csv", list(rpm[0].keys()), rpm)

# load_order.sql
L = [f"-- chunk_{no:03d}: Aveeno/Listerine public data. Self-contained: loads alone into an empty claim_integrity DB",
     "-- (alembic head, 0018) or on top of other chunks, in any order, and can be re-run: every table goes through a",
     "-- staging table + INSERT ... ON CONFLICT DO NOTHING; inferred_truth upserts on sku_id when this chunk's row is newer.",
     "-- Run from this directory:  psql \"$DATABASE_URL\" -v ON_ERROR_STOP=1 -f load_order.sql",
     "\\set ON_ERROR_STOP on",
     "BEGIN;",
     "DO $$ BEGIN IF to_regclass('public.inferred_truth') IS NULL THEN RAISE EXCEPTION "
     "'inferred_truth missing: run alembic upgrade head (0018) first'; END IF; END $$;"]
for t in ["organisation", "brand", "sku", "variant", "page", "snapshot", "extraction", "inferred_truth"]:
    c = ", ".join(COLS[t])
    L.append(f"CREATE TEMP TABLE s_{t} (LIKE {t} INCLUDING DEFAULTS) ON COMMIT DROP;")
    if t == "snapshot":
        for p in parts:
            L.append(f"\\copy s_snapshot({c}) FROM PROGRAM 'gzip -dc {p}' WITH (FORMAT csv, HEADER true)")
    else:
        L.append(f"\\copy s_{t}({c}) FROM '{t}.csv' WITH (FORMAT csv, HEADER true)")
    if t == "inferred_truth":
        upd = ", ".join(f"{x} = EXCLUDED.{x}" for x in COLS[t] if x not in ("id", "sku_id"))
        L.append(f"INSERT INTO {t} ({c}) SELECT {c} FROM s_{t} ON CONFLICT (sku_id) DO UPDATE SET {upd} "
                 f"WHERE {t}.updated_at <= EXCLUDED.updated_at;")
    else:
        L.append(f"INSERT INTO {t} ({c}) SELECT {c} FROM s_{t} ON CONFLICT DO NOTHING;")
for t in COLS:
    L.append(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), GREATEST((SELECT max(id) FROM {t}), 1));")
L.append("COMMIT;")
(OUT / "load_order.sql").write_text("\n".join(L) + "\n", encoding="utf-8")

# chunk stats + manifest + registry
src = Counter(r["source_type"] for r in flat)
cap = sorted(r["captured_at"] for r in flat if r["captured_at"])
stats = {"chunk": no, "flat_rows": len(flat), "loadable_rows": len(ext_c), "unmatched_rows": len(um_new),
         "rows_by_source": dict(src), "rows_by_brand": dict(Counter(r["brand"] for r in flat)),
         "products": len(sku_rows), "pages": len(tables["page"]), "variants": len(tables["variant"]),
         "inferred_truth_rows": len(tables["inferred_truth"]), "snapshot_parts": parts,
         "captured_min": cap[0] if cap else "", "captured_max": cap[-1] if cap else ""}
(OUT / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
man = ROOT / "MANIFEST.csv"
new = not man.exists()
with open(man, "a", encoding="utf-8", newline="") as f:
    w = csv.writer(f)
    if new:
        w.writerow(["chunk", "flat_rows", "loadable_rows", "unmatched_rows", "products", "sources",
                    "captured_min", "captured_max", "commit"])
    w.writerow([f"chunk_{no:03d}", len(flat), len(ext_c), len(um_new), len(sku_rows),
                " ".join(f"{k}:{v}" for k, v in sorted(src.items())), stats["captured_min"], stats["captured_max"], ""])
for s in S:
    pushed[s] = no
for r in um_new:
    st["unmatched"][r["row_key"]] = no
st["n"] = no
REG_P.write_text(json.dumps(REG, ensure_ascii=False), encoding="utf-8")
print(json.dumps(stats))
