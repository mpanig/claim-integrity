"""Seed the pilot: CeraVe Hydrating Facial Cleanser vs. a Rite Aid page with the old formula.

Re-running deletes and recreates the pilot organisation (and everything under it).
Run: uv run python -m app.seed
"""

from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR
from app.models import ApprovedClaim, Brand, Organisation, Page, Sku, Variant
from app.pipeline.extract import ManualExtractor, save_extraction
from app.pipeline.fetch import store_snapshot

FIXTURES = BACKEND_DIR / "fixtures"
PILOT_ORG = "Pilot: CeraVe"
TRUTH_URL = "https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser"
RITEAID_URL = "https://www.riteaid.com/shop/cerave-hydrating-facial-cleanser"
RITEAID_HTML = FIXTURES / "riteaid_cerave_hydrating_cleanser.html"
MANUAL_EXTRACTIONS = FIXTURES / "manual_extractions.json"

TRUTH = {
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
}


def seed(session: Session, extractions_path: Path = MANUAL_EXTRACTIONS) -> dict[str, int]:
    session.execute(delete(Organisation).where(Organisation.name == PILOT_ORG))

    org = Organisation(name=PILOT_ORG)
    session.add(org)
    session.flush()
    brand = Brand(organisation_id=org.id, name="CeraVe")
    session.add(brand)
    session.flush()
    sku = Sku(
        organisation_id=org.id,
        brand_id=brand.id,
        gtin=None,  # fill in from the brand's product master
        name="CeraVe Hydrating Facial Cleanser",
        line="Cleansers",
    )
    session.add(sku)
    session.flush()
    session.add(
        Variant(organisation_id=org.id, sku_id=sku.id, market="US", formula_version="current")
    )
    for field, value in TRUTH.items():
        session.add(
            ApprovedClaim(
                organisation_id=org.id,
                sku_id=sku.id,
                field=field,
                value=value,
                evidence_url=TRUTH_URL,
                approved_by="pilot seed",
            )
        )

    page = Page(
        organisation_id=org.id,
        url=RITEAID_URL,
        source_type="retailer",
        retailer="Rite Aid",
        country="US",
        weight=1.0,
    )
    session.add(page)
    session.flush()

    snapshot = store_snapshot(session, page, RITEAID_HTML.read_text(encoding="utf-8"))
    assert snapshot is not None  # new page, so there is no previous snapshot
    save_extraction(session, ManualExtractor.from_file(extractions_path), snapshot, sku)

    session.commit()
    return {"organisation_id": org.id, "sku_id": sku.id, "page_id": page.id}


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as s:
        print(seed(s))
