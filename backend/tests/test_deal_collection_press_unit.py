"""
Financial press collector (decision D4) — pure functions, no network, no database.

Articles: real Sika Finance / Agence Ecofin pages captured by the audit of 05/10/2026 and a Financial
Afrik page of 21/10/2026, trimmed to their metadata and article container. Feeds: real RSS of 21/10/2026.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from scraping.deals.collect.base import PoliteFetcher
from scraping.deals.collect.press import (
    HOST_DELAYS,
    feed_items,
    is_candidate,
    meta,
    named_roles,
    read_article,
)
from scraping.deals.importer import validate_records

FX = Path(__file__).parent / "fixtures" / "deals" / "press"


def read(name: str):
    content = (FX / name).read_bytes()
    return read_article(meta(content.decode(), "og:url"), content)


def record(name: str) -> dict:
    reading = read(name)
    records = reading.build("DOC", "SRC")
    validate_records(records)
    return records[0]


def roles(rec: dict) -> list[tuple[str, str]]:
    return [(p["role"], p["name"]) for p in rec["participants"]]


def test_sika_named_arranger_who_is_also_lead_manager_and_title_amount():
    rec = record("sika_niger_200md.html")
    assert roles(rec) == [("arranger", "SGI Niger"), ("lead_manager", "SGI Niger")]
    assert (rec["amount"], rec["currency"], rec["unit"], rec["amount_original"]) == (
        Decimal("200"), "XOF", "billions", "200 milliards FCFA")
    assert rec["country_code"] == "NE"
    # Two tranches (6,60 % / 5 ans and 6,90 % / 7 ans): neither rate nor maturity is picked.
    assert "interest_rate" not in rec and "maturity_months" not in rec
    assert read("sika_niger_200md.html").flags == ["press_multi_tranche_terms_not_read"]
    assert rec["use_of_proceeds"].startswith("Les autorités précisent que les fonds collectés serviront à financer")
    src = rec["sources"][0]
    assert (src["source_class"], src["publisher"], src["published_at"]) == ("press_reported", "Sika Finance",
                                                                             date(2024, 12, 13))
    assert src["url"].startswith("https://www.sikafinance.com/marches/le-niger-signe")


def test_ecofin_fact_sheet_roles_amount_rate_and_maturity():
    rec = record("ecofin_baobab_slb.html")
    assert roles(rec) == [("arranger", "CGF Bourse"), ("lead_manager", "CGF Bourse"), ("anchor_investor", "IFC")]
    assert (rec["amount"], rec["interest_rate"], rec["maturity_months"], rec["country_code"]) == (
        Decimal("20"), Decimal("6.8"), 60, "CI")
    assert rec["sources"][0]["field_excerpts"]["amount"] == "fiche de l'opération : « Montant : 20 milliards FCFA »"


def test_names_stop_at_the_sentence_and_the_next_label():
    rec = record("ecofin_afinhab.html")
    assert roles(rec) == [("arranger", "SGCS"), ("lead_manager", "SGCS"), ("arranger", "FGI"), ("lead_manager", "FGI"),
                          ("anchor_investor", "Société Générale Côte d’Ivoire")]
    assert "amount" not in rec  # the title carries two amounts (40 and 100 milliards): none is chosen
    assert roles(record("sika_emergence_plaza.html")) == [("arranger", "SGI HUDSON & Cie")]


def test_no_role_without_an_explicit_role_word():
    assert named_roles("L'opération a été menée avec l'appui de la SGI X et en partenariat avec la Banque Y.") == []
    found = {r[:2] for r in named_roles("Chef de file : SGI Togo. Arrangeur : BOA Capital Securities.")}
    assert found == {("lead_manager", "SGI Togo"), ("arranger", "BOA Capital Securities")}


def test_treasury_auction_reports_and_non_umoa_news_are_out_of_scope():
    assert read("fa_ci_adjudication.html").outcome == "out_of_scope"
    assert not is_candidate("Guinée : Vista Group mobilise 13 milliards FCFA auprès de la BADEA pour financer les PME", "")
    assert not is_candidate("Congo : Des obligations souveraines de 1,55 milliard USD débarquent à la Bourse de Dubaï", "")
    assert not is_candidate("La Côte d’Ivoire adjuge 93,499 milliards FCFA de bons et obligations du trésor", "")
    assert is_candidate("Le Niger signe son retour sur le marché financier avec une émission obligataire de 200 milliards FCFA", "")
    assert is_candidate("AFINHAB clôture son émission de Social Bond de 40 milliards FCFA", "")


def test_real_feeds_are_parsed_and_filtered():
    for name in ("sika_feed.xml", "fa_feed.xml", "ecofin_feed.xml"):
        items = feed_items((FX / name).read_text(encoding="utf-8"))
        assert len(items) == 12 and all(i["link"].startswith("https://www.") for i in items)
        # 21/10/2026: no UMOA deal among the first twelve items (Congo, Guinea, Kenya... are filtered out).
        assert [i["title"] for i in items if is_candidate(i["title"], i["summary"])] == []


def test_paywalled_article_gives_nothing_and_menus_are_not_a_paywall():
    content = (FX / "sika_emergence_plaza.html").read_text(encoding="utf-8")
    assert "Sika Premium" in content and read("sika_emergence_plaza.html").build is not None  # menu link only
    locked = content.replace('arrangé par la SGI HUDSON', "Cet article est réservé aux abonnés. arrangé par la SGI HUDSON")
    reading = read_article(meta(locked, "og:url"), locked.encode())
    assert reading.outcome == "restricted" and reading.build is None


def test_the_article_body_is_never_stored_only_an_evidence_record():
    reading = read("ecofin_baobab_slb.html")
    stored = json.loads(reading.document.content)
    assert reading.document.file_format == "json" and set(stored) == {
        "url", "title", "publisher", "published_at", "note", "quotations", "roles"}
    body_words = len((FX / "ecofin_baobab_slb.html").read_text(encoding="utf-8"))
    assert len(reading.document.content) < body_words / 3
    assert all(len(q) <= 300 for q in stored["quotations"].values())


def test_press_sites_get_five_seconds_between_requests():
    assert set(HOST_DELAYS.values()) == {5.0}
    polite = PoliteFetcher(None, min_delay=1.0, host_delays=HOST_DELAYS)  # type: ignore[arg-type]
    assert polite.host_delays["www.sikafinance.com"] == 5.0


# =========================================================================== audit 22/10/2026 (H4)
def synthetic(title: str, body: str) -> dict | None:
    """A Sika Finance page with this title and body (structure of the captured pages)."""
    html = (f'<html><head><meta property="og:title" content="{title}"/>'
            '<meta property="og:url" content="https://www.sikafinance.com/marches/test"/>'
            '<meta property="article:published_time" content="2026-07-13T10:00:00+00:00"/></head>'
            f'<body><div class="inarticle">{body}</div></body></html>')
    reading = read_article("https://www.sikafinance.com/marches/test", html.encode(), "Mon, 13 Jul 2026 10:00:00 GMT")
    if reading.build is None:
        return None
    return reading.build("DOC", "SRC")[0]


def test_a_profit_or_a_programme_in_the_title_is_never_the_deal_amount():
    rec = synthetic("Sénégal : la banque X affiche un bénéfice de 25 milliards FCFA et prépare un financement",
                    "Arrangeur : SGI Alpha. La banque prépare un emprunt.")
    assert rec is not None and "amount" not in rec
    rec = synthetic("Côte d'Ivoire : un programme de financement de 1 500 milliards FCFA",
                    "Arrangeur : SGI Beta. Le Trésor mobilise des ressources.")
    assert rec is not None and "amount" not in rec


def test_the_exchange_city_never_gives_the_country():
    rec = synthetic("La société Gamma lève 20 milliards FCFA",
                    "Les titres seront cotés à la BRVM d'Abidjan. Arrangeur : SGI Gamma Capital.")
    assert rec is not None and "country_code" not in rec


def test_coverage_rate_and_unrelated_duration_are_not_terms():
    rec = synthetic("Togo : un emprunt obligataire de 30 milliards FCFA",
                    "Le taux de couverture de 150 % a été atteint. Sur 5 ans, le chiffre d'affaires a doublé. "
                    "Arrangeur : SGI Delta.")
    assert rec is not None and "interest_rate" not in rec and "maturity_months" not in rec
    rec = synthetic("Togo : un emprunt obligataire de 30 milliards FCFA",
                    "L'emprunt est remboursable sur 7 ans au taux de 6,5 %. Arrangeur : SGI Delta.")
    assert (rec["maturity_months"], rec["interest_rate"]) == (84, Decimal("6.5"))


def test_an_article_naming_one_isin_meets_the_primary_deal():
    """Audit 22/10/2026 (H3): the same security with the same amount is a candidate (never a merge)."""
    from datetime import date as day

    from scraping.deals.duplicates import DealFacts, is_candidate, matched_criteria

    rec = synthetic("Sénégal : l'Etat lève 52,3 milliards FCFA sur le marché des titres publics",
                    "Les obligations SN0000004862 ont été souscrites. Arrangeur : SGI Epsilon.")
    assert rec["isin"] == "SN0000004862"
    press = DealFacts(id="p", isin=rec["isin"], amount=rec["amount"], currency=rec["currency"], unit=rec["unit"])
    umoa = DealFacts(id="u", isin="SN0000004862", value_date=day(2026, 4, 14), amount=Decimal("52285.76"),
                     currency="XOF", unit="millions")
    criteria = matched_criteria(press, umoa)
    assert {"isin", "undated_isin", "currency_amount"} <= set(criteria) and is_candidate(criteria)
    other = DealFacts(id="o", isin="SN0000004862", value_date=day(2026, 6, 1), amount=Decimal("9000"),
                      currency="XOF", unit="millions")  # a re-opening with another amount: not proposed
    assert not is_candidate(matched_criteria(press, other))
