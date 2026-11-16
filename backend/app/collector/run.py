"""Run the collector from the command line.

  uv run python -m app.collector.run --brand CeraVe --sku "Hydrating Facial Cleanser" --budget 50

--sku matches any product of the brand whose name contains the text (repeatable);
leave it out to collect for every product of the brand.
"""

import argparse
import json

from sqlalchemy import func, select

from app.collector.agent import collect
from app.db import SessionLocal
from app.models import Brand, SourceCandidate, Sku


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public data about a brand and its products.")
    parser.add_argument("--brand", required=True, help="brand name, e.g. CeraVe")
    parser.add_argument("--sku", action="append", default=[], help="part of a product name (repeatable)")
    parser.add_argument("--budget", type=int, default=50, help="maximum HTTP requests for the run")
    args = parser.parse_args()

    with SessionLocal() as s:
        brand = s.scalar(select(Brand).where(func.lower(Brand.name) == args.brand.lower()))
        if brand is None:
            raise SystemExit(f"No brand named {args.brand!r}. Add it in the app or seed the pilot first.")
        skus = s.scalars(select(Sku).where(Sku.brand_id == brand.id)).all()
        if args.sku:
            skus = [k for k in skus if any(part.lower() in k.name.lower() for part in args.sku)]
            if not skus:
                raise SystemExit(f"No {brand.name} product matches {args.sku}.")
        print(f"Collecting for {brand.name}: {', '.join(k.name for k in skus)} (budget {args.budget} requests)")
        run = collect(s, brand.id, [k.id for k in skus], args.budget)

        print(f"\nRun {run.id}: {run.status}. {run.found} new candidates, {run.fetched} pages stored, {run.requests_used} requests.")
        print("\nConnectors:")
        for name, st in run.stats.items():
            detail = st.get("reason") or ", ".join(f"{k} {v}" for k, v in st.items() if k != "status")
            print(f"  {name:18} {st['status']:8} {detail}")
        rows = s.scalars(select(SourceCandidate).where(SourceCandidate.run_id == run.id).order_by(SourceCandidate.status, SourceCandidate.connector)).all()
        print("\nCandidates:")
        for r in rows:
            fields = f" fields={','.join(r.extracted_fields)}" if r.extracted_fields else ""
            print(f"  [{r.status.value:12}] {r.connector:17} {r.url}{fields}")
            if r.fetch_note:
                print(f"  {'':15} {r.fetch_note}")
        if run.errors:
            print("\nErrors:\n  " + "\n  ".join(json.dumps(e) for e in run.errors))
        print(f"\nLLM: {json.dumps(run.cost)}")


if __name__ == "__main__":
    main()
