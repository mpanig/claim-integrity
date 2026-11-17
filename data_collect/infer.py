"""inferred_truth.csv (alembic 0018 schema) built the way app/pipeline/truth.py builds it.

Uses the app's own normalisers and majority() logic (imported from backend/app/pipeline), on the per-table CSVs.
Where a field has more than one candidate, the pick is Claude's, made in a Claude Code session with the same
instruction _claude_pick sends (no ANTHROPIC_API_KEY in backend/.env, so the app could not call it). The picks
live in picks.json: {sku_id: {field: {"index": i, "reason": "..."}}}.

usage (backend venv, PYTHONPATH=backend):
  infer.py DIR candidates            -> DIR/../truth_candidates.json  (what to pick from)
  infer.py DIR write picks.json      -> DIR/inferred_truth.csv, DIR/inferred_truth_reasons.csv
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from app.pipeline.compare import COMPARED_FIELDS
from app.pipeline.truth import _empty, majority

csv.field_size_limit(10**9)
D = Path(sys.argv[1])
MODE = sys.argv[2]
ID0 = 100000

pages = {r["id"]: r for r in csv.DictReader(open(D / "page.csv", encoding="utf-8"))}
snaps = {r["snapshot_id"]: r for r in csv.DictReader(open(D / "snapshot_index.csv", encoding="utf-8"))}
skus = {r["id"]: r for r in csv.DictReader(open(D / "sku.csv", encoding="utf-8"))}
by_sku = defaultdict(list)
for e in csv.DictReader(open(D / "extraction.csv", encoding="utf-8")):
    s = snaps[e["snapshot_id"]]
    by_sku[e["sku_id"]].append((int(e["id"]), s["fetched_at"], s["page_id"], json.loads(e["fields"])))


def sources(sku_id):
    """Same as truth._sources: latest extraction per page, newest first; (ex id, label, weight, values)."""
    rows = sorted(by_sku[sku_id], key=lambda x: (x[1], x[0]), reverse=True)
    seen, out = set(), []
    for ex_id, _, page_id, fields in rows:
        if page_id in seen:
            continue
        seen.add(page_id)
        p = pages[page_id]
        values = {f: (fields.get(f) or {}).get("value") for f in COMPARED_FIELDS}
        out.append((ex_id, p["retailer"] or p["url"], float(p["weight"] or 1.0), values))
    return out


def digest(src, use_claude=False):
    # truth.refresh_inferred: sha256(json.dumps([s[0] for s in sorted(sources)] + [use_claude]))
    return hashlib.sha256(json.dumps([s[0] for s in sorted(src)] + [use_claude]).encode()).hexdigest()


def vkey(field, v):
    from app.pipeline.truth import _norm
    return hashlib.sha1(_norm(field, v).encode()).hexdigest()[:8]


def short(field, v):
    if field == "ingredients":
        return f"{len(v)} items: " + ", ".join(v[:6]) + (" ..." if len(v) > 6 else "")
    if isinstance(v, list):
        return ", ".join(map(str, v))
    return str(v)[:160]


if MODE == "candidates":
    done = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")) if len(sys.argv) > 3 else {}
    out = {}
    for sku_id in sorted(by_sku, key=int):
        src = sources(sku_id)
        fields, agreement, cands = majority(src)
        multi = {f: c for f, c in cands.items() if len(c) > 1}
        # only list decisions not already made for exactly this candidate set
        multi = {f: c for f, c in multi.items()
                 if done.get(sku_id, {}).get(f, {}).get("cands") != sorted(vkey(f, x["value"]) for x in c)}
        if multi:
            out[sku_id] = {"name": skus[sku_id]["name"], "n_sources": len(src),
                           "fields": {f: [f"[{vkey(f, c['value'])}] {short(f, c['value'])} (w{c['weight']}; {'; '.join(c['pages'])[:150]})"
                                          for c in cs] for f, cs in multi.items()},
                           "cands": {f: sorted(vkey(f, x["value"]) for x in cs) for f, cs in multi.items()}}
    (D.parent / "truth_candidates.json").write_text(json.dumps(out, indent=0, ensure_ascii=False), encoding="utf-8")
    print("skus with sources", len(by_sku), "skus needing picks", len(out),
          "field decisions", sum(len(v["fields"]) for v in out.values()))
elif MODE == "autopick":
    # Claude's decision rules after reviewing the candidate sets (truth_candidates.txt), applied to every
    # multi-candidate field, same instruction as truth._claude_pick: pick the value most likely to match the
    # manufacturer's current product; brand sites and higher page weight are more reliable; old formulas linger
    # on retailer pages; only choose from the listed values.
    import re as _re

    def kind(label):
        return "brand" if "brand site" in label else "retailer" if any(
            k in label for k in ("Amazon", "Walmart", "Target", "CVS", "Walgreens", "Ulta", "Boots")) else "db"

    SIZE = _re.compile(r"\d+(\.\d+)?\s*(fl\.?\s*oz|oz|ml|g)\b|,\s*\d", _re.I)
    picks = {}
    for sku_id in sorted(by_sku, key=int):
        src = sources(sku_id)
        fields, agreement, cands = majority(src)
        for f, cs in cands.items():
            if len(cs) < 2:
                continue

            def rank(c):
                kinds = [kind(p) for p in c["pages"]]
                has_brand = "brand" in kinds
                v = c["value"]
                if f == "name":
                    tidy = 0 if SIZE.search(str(v)) else 1
                    return (has_brand, c["weight"], tidy, -len(str(v)))
                if f == "ingredients":
                    return (has_brand, c["weight"], len(v or []))
                return (has_brand, "retailer" not in kinds or has_brand, c["weight"], len(v or []))

            best = max(cs, key=rank)
            kinds = sorted({kind(p) for p in best["pages"]})
            why = {
                "name": "brand-site name with most page weight; tie → name without size/pack suffix",
                "ingredients": "brand-site INCI list preferred over crowd-sourced Open Facts; then weight; then most complete list",
            }.get(f, "manufacturer's own site preferred over retailer copies (old formulas linger there); then page weight; then most complete statement")
            alt = len(cs) - 1
            picks.setdefault(sku_id, {})[f] = {
                "key": vkey(f, best["value"]), "cands": sorted(vkey(f, x["value"]) for x in cs),
                "reason": f"{why}. Chosen from {', '.join(kinds)} source(s): {'; '.join(best['pages'])[:200]}; {alt} other candidate(s)."}
    Path(sys.argv[3]).write_text(json.dumps(picks, indent=1, ensure_ascii=False), encoding="utf-8")
    print("picks for", len(picks), "skus,", sum(len(v) for v in picks.values()), "fields")
elif MODE == "write":
    picks = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
    REG_P = Path(sys.argv[4])
    REG = json.loads(REG_P.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    w = csv.writer(open(D / "inferred_truth.csv", "w", newline="", encoding="utf-8"))
    w.writerow(["id", "sku_id", "fields", "agreement", "method", "sources", "source_hash", "updated_at"])
    rw = csv.writer(open(D / "inferred_truth_reasons.csv", "w", newline="", encoding="utf-8"))
    rw.writerow(["sku_id", "field", "picked_index", "picked_value", "chosen_sources", "n_candidates", "agreement", "reason"])
    n = 0
    stats = {"rows": 0, "claude": 0, "majority": 0, "picked_fields": 0, "picked_non_majority": 0}
    for sku_id in sorted(by_sku, key=int):
        src = sources(sku_id)
        if not src:
            continue
        fields, agreement, cands = majority(src)
        method = "majority"
        sp = picks.get(sku_id, {})
        multi = [f for f, c in cands.items() if len(c) > 1]
        if multi:
            keys = {f: [vkey(f, c["value"]) for c in cands[f]] for f in multi}
            missing = [f for f in multi if sp.get(f, {}).get("key") not in keys[f]]
            if missing:
                sys.exit(f"sku {sku_id}: no valid pick for {missing}")
            for f in multi:
                i = keys[f].index(sp[f]["key"])
                fields[f] = cands[f][i]["value"]
                agreement[f] = round(cands[f][i]["weight"] / sum(c["weight"] for c in cands[f]), 3)
                stats["picked_fields"] += 1
                stats["picked_non_majority"] += i != 0
                rw.writerow([sku_id, f, i, json.dumps(cands[f][i]["value"], ensure_ascii=False)[:500],
                             "; ".join(cands[f][i]["pages"]), len(cands[f]), agreement[f], sp[f]["reason"]])
            method = "claude"
        n += 1
        stats[method] += 1
        # stable id per product (registry), so every chunk carries the same inferred_truth id for a sku
        itm = REG.setdefault("inferred_truth", {})
        if sku_id not in itm:
            nxt = REG.setdefault("_next", {}).get("inferred_truth", ID0 + 1)
            itm[sku_id] = nxt
            REG["_next"]["inferred_truth"] = nxt + 1
        w.writerow([itm[sku_id], sku_id, json.dumps(fields, ensure_ascii=False), json.dumps(agreement), method, len(src),
                    digest(src, use_claude=False), now])
    stats["rows"] = n
    (D / "inferred_truth_stats.json").write_text(json.dumps(stats, indent=1))
    REG_P.write_text(json.dumps(REG, ensure_ascii=False), encoding="utf-8")
    print(stats)
