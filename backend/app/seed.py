"""Seed the pilot organisation.

- CeraVe Hydrating Facial Cleanser vs. a Rite Aid page showing the old formula
- Aveeno Calm + Restore Nourishing Oat Cleanser vs. Hannaford and Kenvue Pro pages

All retailer pages are hand-written stand-ins in fixtures/, not scraped copies.
Re-running deletes and recreates the pilot organisation (and everything under it).

Run: uv run python -m app.seed [--no-run] [--demo-history] [--demo-ai]
"""

import argparse
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models import ApprovedClaim, Brand, Organisation, Page, Sku, TeamMember, Variant
from app.pipeline.extract import ManualExtractor, save_extraction
from app.pipeline.fetch import store_snapshot
from app.pipeline.run import run_for_sku
from app.ai.demo import generate_demo_answers
from app.ai.crawlers import generate_demo_crawls
from app.ai.llms_txt import generate_demo_checks
from app.ai.aeo_alerts import evaluate as evaluate_aeo_alerts
from app.ai.outreach import generate_demo_outreach
from app.ai.readiness import generate_demo_grades
from app.ai.referrals import generate_demo_referrals
from app.ai.library import seed_library
from app.audit.run import seed_brand_pages
from app.services.trends import generate_demo_history

FIXTURES = BACKEND_DIR / "fixtures"
PILOT_ORG = "Pilot"
OLD_PILOT_ORGS = ("Pilot: CeraVe",)  # name used by the phase 1 seed
MANUAL_EXTRACTIONS = FIXTURES / "manual_extractions.json"

RITEAID_URL = "https://www.riteaid.com/shop/cerave-hydrating-facial-cleanser"

CERAVE: dict[str, Any] = {
    "brand": "CeraVe",
    "name": "CeraVe Hydrating Facial Cleanser",
    "line": "Cleansers",
    "truth_url": "https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser",
    "truth": {
        "ingredients": [
            "Aqua/Water/Eau", "Glycerin", "Cetearyl Alcohol", "PEG-40 Stearate", "Stearyl Alcohol",
            "Potassium Phosphate", "Ceramide NP", "Ceramide AP", "Ceramide EOP", "Carbomer",
            "Glyceryl Stearate", "Behentrimonium Methosulfate", "Sodium Lauroyl Lactylate",
            "Sodium Hyaluronate", "Cholesterol", "Phenoxyethanol", "Disodium EDTA",
            "Dipotassium Phosphate", "Tocopherol", "Phytosphingosine", "Xanthan Gum",
            "Cetyl Alcohol", "Polysorbate 20", "Ethylhexylglycerin",
        ],
        "free_from": ["Free of Added Fragrance"],
        "claims": ["Non-comedogenic"],
        "seals": ["NEA Seal of Acceptance"],
    },
    "pages": [
        {
            "url": RITEAID_URL,
            "source_type": "retailer",
            "retailer": "Rite Aid",
            "weight": 1.0,
            "html": "riteaid_cerave_hydrating_cleanser.html",
        }
    ],
}

AVEENO: dict[str, Any] = {
    "brand": "Aveeno",
    "name": "Aveeno Calm + Restore Nourishing Oat Cleanser",
    "line": "Calm + Restore",
    "truth_url": "https://www.aveeno.com/products/calm-restore-nourishing-oat-cleanser",
    "truth": {
        "ingredients": [
            "Water", "Glycerin", "Butylene Glycol", "Avena Sativa (Oat) Kernel Flour",
            "Polysorbate 20", "Poloxamer 188", "Zea Mays (Corn) Starch",
            "Acrylates/C10-30 Alkyl Acrylate Crosspolymer", "Caprylyl Glycol", "Phenoxyethanol",
            "Disodium EDTA", "Ethylhexylglycerin", "Sodium Polyacrylate", "Sodium Hydroxide",
            "Chrysanthemum Parthenium (Feverfew) Flower/Leaf/Stem Juice", "Sodium Hyaluronate",
        ],
    },
    "pages": [
        {
            "url": "https://www.hannaford.com/product/aveeno-calm-restore-nourishing-oat-cleanser",
            "source_type": "retailer",
            "retailer": "Hannaford",
            "weight": 1.0,
            "html": "hannaford_aveeno_oat_cleanser.html",
        },
        {
            "url": "https://www.kenvuepro.com/aveeno/calm-restore-nourishing-oat-cleanser",
            "source_type": "professional",
            "retailer": "Kenvue Pro",
            "weight": 0.7,
            "html": "kenvuepro_aveeno_oat_cleanser.html",
        },
    ],
}

PRODUCTS = [CERAVE, AVEENO]

# Sample team so owner dropdowns have people in them. Fictional names.
SAMPLE_TEAM = [
    ("Demo CMO", "cmo", None),
    ("Sam (CeraVe brand manager)", "brand_manager", "CeraVe"),
    ("Alex (Aveeno brand manager)", "brand_manager", "Aveeno"),
    ("Priya (E-commerce)", "ecommerce", None),
    ("Jordan (Regulatory)", "regulatory", None),
    ("Agency team", "agency", None),
]
TRUTH = CERAVE["truth"]  # kept for the compare tests
# Intended positioning per brand (attribute keys from app.ai.perception). Real configuration, not demo.
POSITIONING = {
    "CeraVe": ["barrier", "derm", "hydrating", "value", "gentle"],
    "Aveeno": ["natural", "gentle", "sensitive", "eczema", "hydrating"],
}


def _seed_product(
    session: Session, org: Organisation, product: dict[str, Any], extractor: ManualExtractor
) -> Sku:
    brand = Brand(organisation_id=org.id, name=product["brand"], positioning=POSITIONING.get(product["brand"], []))
    session.add(brand)
    session.flush()
    sku = Sku(
        organisation_id=org.id,
        brand_id=brand.id,
        gtin=None,  # fill in from the brand's product master
        name=product["name"],
        line=product["line"],
    )
    session.add(sku)
    session.flush()
    session.add(Variant(organisation_id=org.id, sku_id=sku.id, market="US", formula_version="current"))
    for field, value in product["truth"].items():
        session.add(
            ApprovedClaim(
                organisation_id=org.id,
                sku_id=sku.id,
                field=field,
                value=value,
                evidence_url=product["truth_url"],
                approved_by="pilot seed",
            )
        )
    for spec in product["pages"]:
        page = Page(
            organisation_id=org.id,
            url=spec["url"],
            source_type=spec["source_type"],
            retailer=spec["retailer"],
            country="US",
            weight=spec["weight"],
        )
        session.add(page)
        session.flush()
        snapshot = store_snapshot(session, page, (FIXTURES / spec["html"]).read_text(encoding="utf-8"))
        assert snapshot is not None  # new page, so there is no previous snapshot
        save_extraction(session, extractor, snapshot, sku)
    return sku


def seed(
    session: Session, extractions_path: Path = MANUAL_EXTRACTIONS, run_checks: bool = True
) -> dict[str, Any]:
    session.execute(delete(Organisation).where(Organisation.name.in_((PILOT_ORG, *OLD_PILOT_ORGS))))
    org = Organisation(name=PILOT_ORG)
    session.add(org)
    session.flush()

    extractor = ManualExtractor.from_file(extractions_path)
    skus = {p["brand"]: _seed_product(session, org, p, extractor) for p in PRODUCTS}
    for name, role, brand in SAMPLE_TEAM:
        session.add(
            TeamMember(
                organisation_id=org.id,
                name=name,
                role=role,
                brand_id=skus[brand].brand_id if brand else None,
            )
        )
    session.commit()

    seed_library(session, org)  # AI prompt library, personas, competitors, aliases (real config)
    seed_brand_pages(session, org.id)  # each product's brand page, for the site audit
    if run_checks:
        for sku in skus.values():
            run_for_sku(session, sku)
    return {"organisation_id": org.id, "sku_ids": {b: s.id for b, s in skus.items()}}


if __name__ == "__main__":
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-run", action="store_true", help="do not run checks after seeding")
    parser.add_argument(
        "--demo-history",
        action="store_true",
        help="also generate 12 weeks of score history and sample AI answers, marked as demo data in the UI",
    )
    parser.add_argument(
        "--demo-ai",
        action="store_true",
        help="only (re)generate the AEO / GEO demo data (answers, grades, llms.txt, logs, referrals, outreach, alerts); never touches non-demo data",
    )
    args = parser.parse_args()
    with SessionLocal() as s:
        if args.demo_ai and not args.demo_history:
            print(f"demo AI answers: {generate_demo_answers(s)} (labelled 'Demo data' in the UI)")
            print(f"demo page grades: {generate_demo_grades(s)} (labelled 'Demo data' in the UI)")
            print(f"demo llms.txt checks: {generate_demo_checks(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AI crawler hits: {generate_demo_crawls(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AI referral sessions: {generate_demo_referrals(s)} (labelled 'Demo data' in the UI)")
            print(f"demo outreach rows: {generate_demo_outreach(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AEO alerts: {len(evaluate_aeo_alerts(s))} (labelled 'Demo data' in the UI)")
            raise SystemExit(0)
        print(seed(s, run_checks=not args.no_run))
        if args.demo_history:
            print(f"demo history: {generate_demo_history(s)} snapshots (labelled 'Demo data' in the UI)")
            print(f"demo AI answers: {generate_demo_answers(s)} (labelled 'Demo data' in the UI)")
            print(f"demo page grades: {generate_demo_grades(s)} (labelled 'Demo data' in the UI)")
            print(f"demo llms.txt checks: {generate_demo_checks(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AI crawler hits: {generate_demo_crawls(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AI referral sessions: {generate_demo_referrals(s)} (labelled 'Demo data' in the UI)")
            print(f"demo outreach rows: {generate_demo_outreach(s)} (labelled 'Demo data' in the UI)")
            print(f"demo AEO alerts: {len(evaluate_aeo_alerts(s))} (labelled 'Demo data' in the UI)")
