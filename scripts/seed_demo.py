#!/usr/bin/env python3
"""Phase 13 — seed fresh demonstration data into an empty database via SQL.

Run inside the backend container:
  docker exec umoa13_backend python /app/scripts/seed_demo.py

Or from the host:
  docker exec umoa13_backend python -c "exec(open('/app/scripts/seed_demo.py').read())"

This script uses SQLAlchemy directly (same as the integration tests) to seed
institutions, sources, documents, financial data (including one with
"scope not detected"), and deals with participants linking to institutions.
"""
import asyncio
import os
import sys
from pathlib import Path

backend_dir = str(Path(__file__).resolve().parents[1] / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
sys.path.insert(0, "/app")


async def seed():
    from datetime import UTC, datetime
    from decimal import Decimal
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source
    from app.models.review_event import FinancialDataReviewEvent

    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        try:
            dsn = get_settings().database_url
        except Exception:
            host = os.environ.get("POSTGRES_HOST", "localhost")
            port = os.environ.get("POSTGRES_PORT", "5432")
            db = os.environ.get("POSTGRES_DB", "umoa_banking")
            user = os.environ.get("POSTGRES_USER", "umoa_user")
            pwd = os.environ.get("POSTGRES_PASSWORD", "")
            dsn = f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{db}"

    engine = create_async_engine(dsn)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        # Check if already seeded
        count = (await db.execute(select(func.count(Institution.id)))).scalar_one()
        if count > 0:
            print(f"Database already has {count} institutions — skipping seed.")
            # Return existing IDs for the E2E script
            insts = (await db.execute(select(Institution).order_by(Institution.name_official))).scalars().all()
            for inst in insts:
                print(f"  institution: {inst.id} = {inst.name_official}")
            deals_mod = __import__("app.models.deal", fromlist=["Deal"])
            Deal = deals_mod.Deal
            deals = (await db.execute(select(Deal).order_by(Deal.title))).scalars().all()
            for d in deals:
                print(f"  deal: {d.id} = {d.title} [{d.status}]")
            fds = (await db.execute(select(FinancialData).order_by(FinancialData.id))).scalars().all()
            for fd in fds:
                print(f"  financial_data: {fd.id} metric={fd.metric_code} notes={fd.notes!r:.60s}")
            await engine.dispose()
            return

        print("Seeding demo data...")

        # Countries (already exist from migration catalogue)
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()

        # Source
        src = (await db.execute(select(Source))).scalars().first()
        if src is None:
            src = Source(name="BCEAO Publications", url="https://www.bceao.int", source_type="regulator")
            db.add(src)
            await db.flush()

        # Institutions
        inst_a = Institution(
            name_official="Banque Démo A", institution_type="bank",
            country_id=ci.id, status="active",
        )
        inst_b = Institution(
            name_official="Banque Démo B", institution_type="bank",
            country_id=sn.id, status="active",
        )
        inst_c = Institution(
            name_official="Banque Démo C", institution_type="bank",
            country_id=ci.id, status="active",
        )
        db.add_all([inst_a, inst_b, inst_c])
        await db.flush()
        print(f"  inst_a={inst_a.id}  inst_b={inst_b.id}  inst_c={inst_c.id}")

        # Documents
        doc1 = Document(
            title="Rapport annuel Banque A 2024", document_type="annual_report",
            source_id=src.id, institution_id=inst_a.id,
            download_status="downloaded", extraction_status="extracted",
            page_count=42, period_year=2024,
        )
        doc2 = Document(
            title="Rapport annuel Banque B 2024", document_type="annual_report",
            source_id=src.id, institution_id=inst_b.id,
            download_status="downloaded", extraction_status="extracted",
            page_count=38, period_year=2024,
        )
        doc3 = Document(
            title="Rapport annuel Banque C 2024", document_type="annual_report",
            source_id=src.id, institution_id=inst_c.id,
            download_status="downloaded", extraction_status="extracted",
            page_count=30, period_year=2024,
        )
        db.add_all([doc1, doc2, doc3])
        await db.flush()

        # Helper for financial data
        def fd(inst, doc, metric, year, value, *, status="verified", scope="individual", notes=None):
            extra = {}
            if status == "verified":
                extra = {"verified_at": datetime.now(UTC), "verified_by": "seed-demo"}
            row = FinancialData(
                institution_id=inst.id, source_id=src.id, document_id=doc.id,
                metric_code=metric, scope=scope, period_type="annual",
                period_year=year, value_original=str(value),
                currency_original="XOF",
                value_normalized=None if value is None else Decimal(str(value)),
                unit_normalized="unit", currency_normalized="XOF",
                extraction_method="pdf_table", status=status,
                page_number=1, notes=notes, **extra,
            )
            db.add(row)
            return row

        # Financial data rows
        # Banque A
        fd_a1 = fd(inst_a, doc1, "total_actifs", 2024, 1000000000)
        fd_a2 = fd(inst_a, doc1, "total_actifs", 2023, 900000000)
        fd_a3 = fd(inst_a, doc1, "capitaux_propres", 2024, 100000000, status="reviewed")
        fd_a4 = fd(inst_a, doc1, "depots_clients", 2024, 500000000, status="extracted")
        fd_a5 = fd(inst_a, doc1, "depots_clients", 2024, 520000000, status="extracted")  # competing observation

        # Banque B
        fd_b1 = fd(inst_b, doc2, "total_actifs", 2024, 800000000)
        fd_b2 = fd(inst_b, doc2, "total_actifs", 2023, 700000000)
        fd_b3 = fd(inst_b, doc2, "capitaux_propres", 2024, 80000000, status="reviewed")

        # Banque C — has "scope not detected" issue
        fd_c1 = fd(inst_c, doc3, "total_actifs", 2023, 650000000)
        fd_c2 = fd(inst_c, doc3, "total_actifs", 2024, 750000000,
                   status="verified",
                   notes="scope not detected | Review: Périmètre vérifié : comptes individuels (E2E) | Verification: Périmètre vérifié : comptes individuels (E2E)")

        await db.flush()

        # Review events for auditable records
        for row_obj, action, prev, new in [
            (fd_a3, "review", "extracted", "reviewed"),
            (fd_b3, "review", "extracted", "reviewed"),
        ]:
            db.add(FinancialDataReviewEvent(
                financial_data_id=row_obj.id, action=action,
                previous_status=prev, new_status=new,
                actor="seed-demo", reason="Seed demo review",
            ))

        await db.flush()

        # Deals with participants (institution links)
        deals_mod = __import__("app.models.deal", fromlist=["Deal", "DealSource", "DealParticipant"])
        Deal = deals_mod.Deal
        DealSource = deals_mod.DealSource
        DealParticipant = deals_mod.DealParticipant

        deal1 = Deal(
            title="Prêt syndiqué démo — Autoroute du Nord",
            deal_type="syndicated_loan", country_id=sn.id,
            sector="infrastructure", project_name="Autoroute du Nord",
            amount=Decimal("25000000000"), currency="XOF", unit="units",
            amount_original="25 milliards FCFA",
            signing_date=datetime(2024, 3, 15).date(),
            status="needs_review",
        )
        deal2 = Deal(
            title="Financement démo de l'autoroute du Nord (Sénégal)",
            deal_type="project_finance", country_id=sn.id,
            sector="infrastructure", project_name="Autoroute du Nord",
            amount=Decimal("15000000000"), currency="XOF", unit="units",
            status="verified",
            verified_at=datetime.now(UTC), verified_by="seed-demo",
        )
        deal3 = Deal(
            title="Emprunt obligataire démo EUR",
            deal_type="bond", country_id=ci.id,
            sector="financial", amount=Decimal("10000000"), currency="EUR", unit="units",
            amount_original="10 millions EUR",
            status="needs_review",
        )
        db.add_all([deal1, deal2, deal3])
        await db.flush()

        # Deal sources
        ds1 = DealSource(deal_id=deal1.id, document_id=doc1.id, source_id=src.id, page_number=3, excerpt="Tableau des financements")
        ds2 = DealSource(deal_id=deal2.id, document_id=doc2.id, source_id=src.id, page_number=7)
        ds3 = DealSource(deal_id=deal3.id, document_id=doc3.id, source_id=src.id, page_number=12)
        db.add_all([ds1, ds2, ds3])
        await db.flush()

        # Deal participants WITH institution links
        # Deal 1: Banque A as arranger (has institution_id), État du Sénégal as borrower (no institution_id), Banque B as lender (has institution_id)
        db.add(DealParticipant(deal_id=deal1.id, participant_name="Banque Démo A", institution_id=inst_a.id, role="arranger", deal_source_id=ds1.id))
        db.add(DealParticipant(deal_id=deal1.id, participant_name="État du Sénégal", role="borrower", deal_source_id=ds1.id))
        db.add(DealParticipant(deal_id=deal1.id, participant_name="Banque Démo B", institution_id=inst_b.id, role="lender", deal_source_id=ds1.id))

        # Deal 2: Etat du Senegal borrower only (no institution_id)
        db.add(DealParticipant(deal_id=deal2.id, participant_name="Etat du Senegal", role="borrower", deal_source_id=ds2.id))

        # Deal 3: Société démo Y as borrower (no institution_id), Banque B as arranger (has institution_id)
        db.add(DealParticipant(deal_id=deal3.id, participant_name="Société démo Y", role="borrower", deal_source_id=ds3.id))
        db.add(DealParticipant(deal_id=deal3.id, participant_name="Banque Démo B", institution_id=inst_b.id, role="arranger", deal_source_id=ds3.id))

        # Import audit events for deals
        db.add(FinancialDataReviewEvent(deal_id=deal1.id, action="import", previous_status="none", new_status="needs_review", actor="seed-demo", reason="Structured import: seed_demo.py"))
        db.add(FinancialDataReviewEvent(deal_id=deal2.id, action="import", previous_status="none", new_status="needs_review", actor="seed-demo", reason="Structured import: seed_demo.py"))
        db.add(FinancialDataReviewEvent(deal_id=deal2.id, action="review", previous_status="needs_review", new_status="reviewed", actor="seed-demo", reason="Demo review"))
        db.add(FinancialDataReviewEvent(deal_id=deal2.id, action="verify", previous_status="reviewed", new_status="verified", actor="seed-demo", reason="Demo verification"))
        db.add(FinancialDataReviewEvent(deal_id=deal3.id, action="import", previous_status="none", new_status="needs_review", actor="seed-demo", reason="Structured import: seed_demo.py"))

        await db.commit()
        print("Demo data seeded successfully.")

        # Print IDs for E2E script
        print(f"  inst_a={inst_a.id}")
        print(f"  inst_b={inst_b.id}")
        print(f"  inst_c={inst_c.id}")
        print(f"  deal1={deal1.id} (needs_review, has institution links)")
        print(f"  deal2={deal2.id} (verified, borrower only)")
        print(f"  deal3={deal3.id} (needs_review, has institution link)")
        print(f"  fd_c2={fd_c2.id} (scope not detected)")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
